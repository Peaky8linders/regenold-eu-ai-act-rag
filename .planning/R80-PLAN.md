# R80 Plan — next steps after R77–R79

Hand-off for a **fresh session**. Read top to bottom. The R77–R79
rounds shipped a large change (Stage-2 polish disabled, retrieval +
answer-shaping fixes, a deep-code-review pass). The next round is
**measurement-gated** — do Step 0 before anything else.

## State after R77–R79 (origin/main @ 7a8d0f3)

| PR | Round | What shipped |
| -- | ----- | ------------ |
| #104 | R77 | I1 Stage-2 LLM polish OFF by default · I2 removed the `"high-risk"`→Art.6 anchor shadow · I4 per-reference description augmenter · I6 shape-aware QA ref budget 5→3 |
| #105 | R78 | `_hard_truncate_at_clause` 600-char backstop for enumerated answers (env `REGENOLD_HARD_CHAR_CAP`, **default OFF**) |
| #107 | R79 | 7 deep-code-review correctness fixes (cache key, prepend dedup, Unicode hyphen, augmenter period, chapter confidence boost, env parse, truncate regex) |

**The deterministic answer is now the entire shipped product** — R77
disabled the Stage-2 LLM polish (it measured net-negative on every
LLM-judge axis + 3.5× slower in the R76 live representative-100 run).

### Env knobs now in play (defaults)

| Env var | Default | Effect |
| ------- | ------- | ------ |
| `P2P_GRAPH_RAG_ENABLE_STAGE2` | `0` (off) | master gate for Stage-2 polish |
| `REGENOLD_HARD_CHAR_CAP` | `0` (off) | hard-truncate answers >600 chars |
| `REGENOLD_QA_REF_BUDGET` | `1` (on) | QA ref budget 3 (vs 5) |
| `REGENOLD_REF_DESCRIBE_AUG` | `1` (on) | per-ref description augmenter |

## Step 0 — the hard dependency: live judge re-run

**Nothing in the R80 queue can be prioritised correctly without this.**
R77–R79's wins are on the LIVE LLM-judge axes (refs-faithfulness,
conciseness, tone, latency) — the local davidath bench is BM25-
saturated and structurally cannot measure them (every R77–R79 davidath
A/B came back byte-identical or a wash, by design).

Run, after #104–#107 are deployed to Railway:

```
py -3.12 -m evals.bench.representative_100 --label r79-live --verbose \
  --endpoint "https://regenold-eu-ai-act-rag-production.up.railway.app/api/v1/regenold/eu-ai-act/ask?include_reasoning=true" \
  --api-key <REGENOLD_API_KEY>
py -3.12 -m evals.judge.runner --provider anthropic --concurrency 6 \
  --bench-sidecar evals/bench/results/representative-100-r79-live.json --label r79-live
```

**Use `--provider anthropic` for the judge** — verified in R77 that the
Claude Max wrapper degrades on the heavy refs-faithfulness prompt
(8-row smoke errored 8/8). The judge needs an Anthropic console key.

Compare against the R76 live baseline (the numbers that motivated
R77): live p50 17 s, judge correctness 0.55, refs 0.20, conciseness
0.41, tone 0.76. **R77–R79 targets**: live p50 < 6 s (Stage-2 off),
refs 0.35+, conciseness 0.55+, tone 0.85+. The deterministic-path
judge baseline (R76) was correctness 0.63 / refs 0.23 / conciseness
0.53 / tone 0.85 — live should now climb toward those.

## R80 work queue (prioritise from the Step-0 data)

### A — `REGENOLD_HARD_CHAR_CAP` A/B *(decide ON/OFF)*

R78 shipped it default-OFF: davidath A/B was a wash (Ans Strict
−0.006 / Conciseness +0.004). The real payoff is the binary judge
conciseness axis (R76 flagged 8 answers as ">4 sentences"). Run the
Step-0 live judge once with `REGENOLD_HARD_CHAR_CAP=1` and once OFF;
if judge conciseness lifts materially, flip the default ON in
`models.py` + document.

### B — I3 latency residual *(measurement-gated)*

With Stage-2 off, the live residual was ~5.6 s = network + the
Stage-0 intent-classifier LLM call + the Stage-1 LLM parse. Levers:
* **Stage-0 → Groq** — the R52 code path already exists
  (`REGENOLD_INTENT_PROVIDER=groq` + `GROQ_API_KEY`); flat $0.59/M,
  500+ tok/s. An operator env change — measure the p50 delta.
* **Stage-1 LLM parse** — investigate whether it still earns its
  latency now Stage-2 is gone. The R76 deterministic run (zero LLM)
  beat live on every axis — but that comparison confounds Stage-0/1/2.
  Do NOT disable Stage-1 parse blind; isolate it first.

### C — I5 Neo4j 2-hop live A/B

R77 verified `graph_expand_2hop` is already additive-below-cap (the
plan's suspected "pushes gold past the cap" mechanism does not exist).
The open question is the live A/B: re-run Step-0 with
`REGENOLD_GRAPH_2HOP=0`; the R76 live data showed the `neo4j`
retrieval path at Ref Loose 0.49 vs 0.68 — confirm whether that is
causal or just correlated with harder rows.

### D — I4 augmenter redesign *(judge-driven)*

R79 confirmed `augment_with_ref_descriptions` is **suppressed on
3-sentence answers** — it appends a 4th sentence which the
`MAX_ANSWER_SENTENCES=3` cap (hard rule #2) then drops. It only fires
on 1–2 sentence answers. To make it work on the scenario answers it
was designed for, it must REPLACE the least-descriptive sentence
rather than append. This is a redesign whose only payoff is the judge
refs-faithfulness axis — do it only with the Step-0 judge data in hand.

### E — `_reconcile_references_to_prose` decoupling *(judge-driven)*

R79 found this pass is gated on `stage2_landed`, which is always False
since R77 disabled Stage-2 → the pass is dead in production. It drops
references the prose never describes. Decoupling it from `stage2_landed`
is a measurable change (drops refs → moves Ref Loose/Strict) — A/B on
davidath AND the live judge before shipping.

### F — I7 zero-retrieval-fallback recheck

R76 found 6 in-scope rows hitting the `Art. 1/2/3` floor. R77's I2
(high-risk un-shadow) was expected to shrink that set. Recheck the
count in the Step-0 live sidecar's `retrieval_path` distribution.

## Verification gates (every R80 PR)

* `pytest -q` stays green (R79 left it at **2382 pass / 1 skip**).
* `evals.bench.runner` davidath — no regression: Ref Loose ≥ 0.575,
  Ref Strict ≥ 0.464, Ans Strict ≥ 0.303, Tone 1.0, multi-turn 20/20.
* `evals.regenold.runner` — 276/276.
* `evals.regenold.runner_v2 --local --probe-oos` — 21/21, 0 leaks.

## Load-bearing context / gotchas

* **davidath is BM25-saturated** (R31/R59/R69/R77 — four confirmations).
  Retrieval / anchor / scope changes come back byte-identical on the
  local bench. Do NOT chase davidath lifts from retrieval work — the
  bench is a regression guard, the wins land on the live judge.
* **Multi-agent repo**: `main` advances mid-session; many concurrent
  Claude agents. `git fetch` + base off current `origin/main`; work in
  an isolated `git worktree` placed OUTSIDE the repo tree (sibling
  dir). Check `git log origin/main` before assuming a deliverable is
  unshipped.
* **Stage-2 is OFF**: the deterministic engine answer is the product.
  Every answer-assembly path in `app/routes/regenold.py` is now
  load-bearing.
* **The Max wrapper can't sustain judge volume** — use
  `evals.judge.runner --provider anthropic`.
* CLAUDE.md hard rules still bind: `Article N` / `Annex X` ref format;
  `MAX_ANSWER_SENTENCES = 3` + 600-char soft cap; no overfit to the 3
  PDF example questions; KB stubs ship faithful prose; every citation
  must resolve in `ARTICLE_EXISTENCE`.

## How to reproduce the local benches

```
py -3.12 -m pytest -q                                  # 2382 pass / 1 skip
py -3.12 -m evals.bench.runner --label r80             # 476-item davidath
py -3.12 -m evals.regenold.runner                      # 276 local scenarios
py -3.12 -m evals.regenold.runner_v2 --local --probe-oos --label r80-oos
py -3.12 -m evals.bench.representative_100 --label r80  # deterministic rep-100
```

Run with the main repo's venv from inside the worktree:
`"D:\Claude Projects\regenold-eu-ai-act-rag\.venv\Scripts\python.exe" -m ...`
