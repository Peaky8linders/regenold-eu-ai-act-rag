# R288 — CHECKPOINT / fresh-session handoff

**Date:** 2026-07-24. **Branch:** `main` (⚠ uncommitted — see §1).
**Two jobs left:** (A) finish R288 with a properly-powered A/B, (B) run + judge the
HARD official batch, which has **never been graded by our own instrument**.

---

## 0. Read these first (5 min, saves hours)

* `CLAUDE.md` hard rule #6 — `evals.harness.ab_judge` / gold-bearing A/B is the
  merge gate, davidath is a REGRESSION GUARD ONLY.
* Memory: `project_easyhard_ab_noise_floor_n40.md` ← **the most important new
  finding. Read before designing any A/B.**
* Memory: `project_nli_verifier_measured_dead.md` — do not revisit NLI/torch.
* Memory: `project_ans_metrics_not_comparable.md` — never compare a local Ans
  number to the regenold report.

---

## 1. Uncommitted state on `main` (⚠ hazard)

```
 M app/engines/graph_rag.py      <- R288 Arm-1 (gated OFF)
 M app/routes/regenold.py        <- R288 cache-key entries
?? tests/test_r288_grounding_text.py            (24 tests, all pass)
?? evals/harness/nli_refprecision_sim.py        (NLI/lexical ref-filter sim)
?? evals/harness/nli_discriminative_power.py    (AUC / separation check)
```

⚠ **Railway auto-deploys `main`,** and per `project_multiagent_autocommit_env.md`
automation in this environment has auto-committed `main` mid-session before.
R288 is **default-OFF**, so an accidental deploy is inert on the wire — but do not
`git add -A` (the repo root is littered with `_v_*.py` / `_r_*.py` scratch files
that predate this session). Prefer a worktree for new work.

Also still installed locally from this session: **torch + transformers +
sentence-transformers** (~2.5 GB in `.venv`). Harmless (the only import is behind
the default-OFF NLI path; OOS probe verified 21/21), but the deploy is torch-free —
uninstall if you want local/prod parity.

---

## 2. What R288 established (do not re-derive)

### 2a. Neural NLI citation verification is DEAD — measured
ROC-AUC **0.585** at separating gold from non-gold refs vs **0.749** for the FREE
in-repo `LexicalEntailmentScorer`, at **635 ms/pair vs 2.7**. MNLI cross-encoders
collapse to "neutral" on legal text (75% of pairs < 0.027 entailment). A bigger NLI
model does not fix a training-distribution problem. `REGENOLD_NLI_VERIFY` stays OFF.
Do NOT add torch to `requirements.txt` (plain `torch` on Linux pulls the CUDA stack,
~2.7 GB of wheels → 6-8 GB unpacked → past Railway's ~4 GB image ceiling).

### 2b. The real defect (verified, still open)
`_build_context_references_block` (`app/engines/graph_rag.py`) feeds Stage-2 our
hand-authored KB paraphrase stubs, not the regulation. Measured on the real 110-row
easy batch: **215/322 (67%) of actually-cited refs have NO paragraph-level text**
(`article_requirements_full.py` covers **19 of 131** KB entries and **zero
annexes**), while prompt rule 5b tells the model to "use the EXACT terminology
found in the retrieved articles". That is the `AnsL − RefL = −13.1` signature:
right article, our words.

### 2c. Arm 0 is dead (do not retry)
Wiring up `semantically_relevant_statements` does NOT fix 2b: that field is a dense
hit-list for *different* articles — **zero overlap** with the retrieved set on all
four probe questions (Article-13 question → Art. 79/80/82). Scoped it renders
nothing; unscoped it injects off-context noise.

### 2d. Arm 1 is BUILT and gated OFF
`_render_grounding_text()` fetches the question-relevant **verbatim paragraphs of
the CITED refs** via `provision_text.select_relevant_paragraphs`.
Env: `REGENOLD_GROUNDING_TEXT` (default `0`), `REGENOLD_GROUNDING_REF_CHARS`
(default 1200, clamped 200-4000). Both are in `_engine_cache_key` (R263.2 doctrine).
The question rides on `GraphContext.question` so BOTH block call sites render
identically (R113 guard/prompt parity).

### 2e. Gates already green for Arm 1 (no need to re-run)
davidath QA gate-OFF **byte-identical** (Ans Strict 0.4037 / Ref Loose 0.8394 /
Ref Strict 0.5543 / Ref Conc 0.4395 / Tone 1.0) · 276-runner **255/255** ·
OOS **21/21, 0 leaks** · `tests/test_r288_grounding_text.py` **24/24** ·
touched-surface **zero regressions** (stash A/B; the 12 `_when_wrapper_enabled`
failures are pre-existing under `provider=cli`).

### 2f. ⚠ THE MEASUREMENT PROBLEM — this is why R288 is unfinished
Two `easyhard_ab --limit 40` runs with an **identical baseline arm** did not
reproduce: **20/40 baseline rows changed their `pred_refs`**, baseline `ref_conc`
drifted **+0.053**, and **all three reference axes sign-flipped** between runs. The
harness's "est. Overall uplift" read **+0.14 pp** then **−0.80 pp** on pure
generation variance.

**Only `kw_recall` was stable: +0.0750 and +0.1083** — and it is NOT a length
artifact (it rose **+0.048 on the 14 rows whose answers got SHORTER**).

⇒ A single n=40 live run **cannot** resolve a reference-axis effect of this size.
Any "GOLD LOSS (R142.1)" annotation from one such run may be noise — in run 1 it
flagged −0.021 and run 2 reversed it to +0.017.

---

## 3. JOB A — finish R288 with a powered A/B

**Goal:** decide ship / don't-ship on Arm 1 with a measurement that can actually
resolve it.

**Design (per §2f):** full n (drop `--limit`) **and** ≥3 repeats per arm, reporting
mean ± spread. Do NOT ship on a single run. Budget ~4-6 h of wrapper time; run
arms SEQUENTIALLY (everything funnels to one local Claude Max).

```bash
# live wrapper env (Stage-2 must actually fire)
export OPENAI_API_BASE=http://127.0.0.1:8000/v1
export OPENAI_API_KEY=dummy
export P2P_GRAPH_RAG_PROVIDER=openai_wrapper
# health first — a dead wrapper silently yields a deterministic-only A/B
curl -s http://127.0.0.1:8000/v1/auth/status | head -c 200
```

```bash
# one repeat (repeat with --label r288-pow-2, -3 …)
.venv/Scripts/python.exe -m evals.harness.easyhard_ab --local \
  --label r288-pow-1 \
  --baseline-env REGENOLD_GROUNDING_TEXT=0 \
  --branch-env  REGENOLD_GROUNDING_TEXT=1
```

**Also sweep the budget** — the 1200-char default grew answers **+12%**, and
Answer Conciseness is the ONE axis we lead (96.0 easy / 93.4 hard):
`--branch-env REGENOLD_GROUNDING_REF_CHARS=500` (500 measured kw +0.108 with
answers still growing; try 300/500/800).

**Decision gates:**
1. **KILL:** answer length rises materially across repeats → do not ship (AnsCon
   has zero headroom).
2. **KILL:** `ref_loose` (recall) drops consistently across repeats → R142.1.
3. **SHIP** only if `kw_recall` holds up AND length + recall are flat across
   repeats. Then also run the grounded judge on both arms (§4 pattern) to confirm
   `answer_correctness` moves, since `kw_recall` is only a proxy.

---

## 4. JOB B — run + judge the HARD official batch

**Why:** hard is where we are furthest behind (**73.0**, −14.4 pp vs frontier) and
our own grounded judge has **never** been run on it. `grounded-r286-easy-grounded.json`
exists; there is no hard equivalent. This is the single biggest missing measurement.

```bash
# 1. re-run HARD against deployed prod (110 questions, ~1.5-2 h at 36 s p50)
.venv/Scripts/python.exe -m evals.regenold.run_official_batch \
  --label r288-hard --mode hard \
  --endpoint https://regenold-eu-ai-act-rag-production.up.railway.app/api/v1/regenold/eu-ai-act/ask \
  --api-key "$REGENOLD_API_KEY"          # see memory reference_cloudflare_tunnel_key.md
```

```bash
# 2. grade it (reference-free; scores vs VERBATIM Act text — the right instrument
#    because regenold's gold is NOT in our possession)
.venv/Scripts/python.exe -m evals.judge.grounded \
  --sidecar evals/bench/results/official-r288-hard-hard.ckpt.jsonl \
  --label r288-hard-grounded --provider wrapper --model claude-sonnet-5
```

**Compare against the EASY baseline** (`grounded-r286-easy-grounded.json`,
2026-07-23, n=110):

| axis | easy |
| --- | --- |
| answer_correctness | 0.500 pass (mean factual 0.806) |
| reference_correctness | 0.318 pass — P 0.648 / R 0.913 / F1 0.758 |
| citation_faithfulness | 0.764 |

**What to look for:** the report says hard is worse on every axis (AnsS 60.6 vs
63.6, RefCon 72.1 vs 79.3, Speed 61.7 vs 75.1). Find whether the judge agrees and
**which axis carries the gap** — that is what should drive R289. Read the
per-row `failure_mode` strings, not just the aggregate; on easy they were dominated
by *omitted enumerated conditions* ("omits the four Annex III(3) education
categories", "omits 'prosecute' from the criminal-offence carve-out").

---

## 5. Standing context

**Report baseline (2026-07-14, graded on our 2026-07-07 run):**

| | Overall | AnsL | AnsS | AnsCon | RefL | RefS | RefCon | Tone | Speed |
|---|---|---|---|---|---|---|---|---|---|
| Frontier+Search | 88.1 | 94.4 | 89.1 | 89.1 | 96.1 | 78.5 | 80.7 | 100 | 79.7 |
| 2025 Search | 80.9 | 83.8 | 70.9 | 90.3 | 79.9 | 52.0 | 86.9 | 99.1 | 95.5 |
| **Us easy** | **77.5** | 72.1 | 63.6 | **96.0** | 85.2 | 58.8 | 79.3 | 98.5 | 75.1 |
| **Us hard** | **73.0** | 74.0 | 60.6 | **93.4** | 78.7 | 56.0 | 72.1 | 98.2 | 61.7 |

Overall = plain geometric mean of the 8 axes ⇒ a weak axis drags disproportionately.
Bottleneck is **answer correctness**; AnsCon is the only axis we lead (zero headroom);
**Speed 61.7 hard is the second-worst axis** and the 2026-07-23 re-run still sat at
**36.4 s p50 / 128.9 s max** — worth its own round.

**Post-optimisation re-run (2026-07-23, prod, 110 q, 0 errors, 0 refusals):**
easy refs/answer **3.99 → 2.93 (−27%)**, answer chars 915 → 914, 79% of answers
changed, ref-head Jaccard 0.754, tone 1.0, p50 23.5 s.
Hard: refs 4.02, chars 1177, p50 36.4 s, **pushback conceded 0/110**.
⚠ These are observables, **not** report-scale scores — see `project_ans_metrics_not_comparable.md`.

---

## 6. Traps

* **12 pre-existing test failures** in `test_two_stage_pipeline` /
  `test_graph_rag_bugfixes` under `provider=cli` — verify with a `git stash` A/B
  before blaming your change.
* **Something listens on `127.0.0.1:8080`** on this box, and
  `crag_nli_verifier.score_batch` silently falls back to it. Any local NLI A/B is
  graded by an unidentified stub. (Unfixed; gated OFF so inert.)
* **Deterministic env** for every offline gate:
  `OPENAI_API_BASE=http://127.0.0.1:1/v1 P2P_GRAPH_RAG_PROVIDER=cli`.
  Add `REGENOLD_EXTERNAL_EMBEDDINGS=0` for davidath (R251 non-determinism on
  role-noun rows).
* **Never `?include_reasoning=true` in an eval** — it forces Stage-2 and distorts
  the comparison (R112).
* Any new env flag that flips the engine's answer MUST go in `_engine_cache_key`,
  or a same-process A/B serves the OFF arm's cached output to the ON arm (R263.2).
