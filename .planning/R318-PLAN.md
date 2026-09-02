# R318 — Final optimisation plan: SOTA and beating frontier models

**Authoritative handoff for a fresh session.** Written at the end of R317
(2026-08-07). Everything here is measured. Read `CLAUDE.md` Hard rules +
Validation policy + "Fresh session plug-in" first; this is the action plan.

---

## 0. Where we actually stand — three different scorecards, do not conflate them

### (a) The OFFICIAL regenold scorecard — the one that decides the competition

* We beat **0** baselines. `Overall` is a plain **geometric mean**, so it is
  dominated by the lowest axis.
* `AnsLoose − RefLoose = **−13.1**` for us vs **+3.9** for the 2025 baselines.
* **Answer-Conciseness is the ONLY axis we lead ⇒ zero headroom, pure downside
  risk.** Never "shorten answers" or "add prose" as a strategy without
  measuring it.
* ⚠ **No official formula is disclosed for ANY of the 8 axes** (R280 §5). Local
  `Ans` metrics are provably NOT regenold's — `metrics.py` loose = Jaccard,
  strict = recall, and `loose <= strict` is an identity for us, while the
  official shows `AnsL > AnsS` on 6/6 rows. Do not compare local Ans numbers to
  the report.

### (b) davidath — the REGRESSION GUARD (never a win-measure)

Full 476, under the neutralising env:

| axis | value |
| --- | --- |
| Ans Strict | **0.3545** |
| Ans Loose | 0.1884 |
| Ans Conciseness | 0.6143 |
| Ref Loose | **0.5971** |
| Ref Strict | **0.4748** |
| Ref Conciseness | 0.4319 |
| Tone | 1.0 |

QA-only (137): Ans Strict 0.4072 · Ref Loose 0.8394 · Ref Strict 0.5536.

### (c) The FRONTIER head-to-head — the "are we SOTA?" measure

132 paired rows. Ours = fresh current code, Stage-2 firing. Theirs =
`claude-opus-5` with **no retrieval, no search, no tools** (handicapped on
purpose, so a frontier win is stronger evidence against us).

| axis | ours | frontier | per-row (ours/frontier/tie) |
| --- | --- | --- | --- |
| **Ref Loose (recall)** | **0.8636** | 0.8396 | 18 / 12 / 102 |
| **Keyword recall (answer proxy)** | **0.8376** | 0.7864 | 34 / 19 / 79 |
| Ref Strict (F1) | 0.6461 | **0.6938** | 38 / 58 / 36 |
| Ref Conciseness | 0.4582 | **0.5664** | 29 / 59 / 44 |
| mean predicted refs | 2.88 | 2.59 | |
| latency p50 | 26.0 s | 13.9 s | |

**Read this carefully:**

1. **R280's "our answer layer LOSES to a frontier model" is DEAD.** It was
   kw 78.6 vs 88.6, per-row 4/27 against us; now 34/19 for us.
2. ⚠ **That does NOT mean the official AnsL gap is closed.** `kw_recall` is a
   PROXY. The official answer axes are undisclosed and the official
   `AnsL − RefL = −13.1` still stands. Treat (a) and (c) as separate problems.
3. **Over-citation is the ONLY axis a frontier model still beats us on** —
   Ref Strict −0.048 and Ref Conciseness −0.108 are the SAME defect. We cite
   2.88 refs to their 2.59.

---

## 1. The over-citation lever — the ceiling, and everything that is DEAD

**Ceiling:** an oracle that drops every non-gold ref gains **Ref Strict +0.215 /
Ref Conciseness +0.229 at unchanged recall** (197 non-gold refs across 89 of 132
rows). That is the whole prize. Nothing so far captures any of it.

**R317 measured five rule families. ALL FIVE failed. Do not re-propose:**

| family | why it is dead |
| --- | --- |
| article-IDENTITY blocklist | only 19% of non-gold refs are heads that are never gold. Article 6 wrong 21x / **gold 22x**; corpus-wide Annex III 30/**52**, Article 5 10/**28** |
| positional / top-N clamp | top-2 drops **23 gold**, top-3 **6**, top-4 **1**. A 2.26x protection signal only gets budget-2 to 11. Reproduces R142.1 (lost a live pairwise 11-0, p=0.001) |
| prose-driven pruning | structural no-op — **86%** of wrong refs ARE described (R298/R302) |
| ask-type x provision-role exclusivity | net NEGATIVE on the gold gate; **classifier-fragile** — two competent implementations of the SAME described rule disagree on **30% of rows** and flip the safety verdict from 0 to 11 governing destroyed. 4 further angles rejected at 27, 18, 8 and **2310** gold dropped |
| Chapter III tier exclusivity | clean on FIVE gates then falsified by the full 476: Ref Loose **−0.0160**, **67 gold dropped across 40 scenarios (0 on QA)**. Ships default OFF |

**The generalisable lesson:** the same article head is gold on one question and
wrong on another. No removal rule keyed on identity, position, or prose
survives. **Trimming is a dead end — work the ranker instead.**

---

## 2. The plan — ranked, with the measurement that motivates each

### Step 0 — re-establish baselines (30 min, do this first)

```bash
# davidath FULL (never --qa-only for a reference change — hard rule #7)
OPENAI_API_BASE=http://127.0.0.1:1/v1 P2P_GRAPH_RAG_PROVIDER=cli REGENOLD_EXTERNAL_EMBEDDINGS=0 \
  .venv/Scripts/python.exe -m evals.bench.runner --label r318-base

OPENAI_API_BASE=http://127.0.0.1:1/v1 P2P_GRAPH_RAG_PROVIDER=cli REGENOLD_EXTERNAL_EMBEDDINGS=0 \
  .venv/Scripts/python.exe -m evals.regenold.runner --label r318-276

OPENAI_API_BASE=http://127.0.0.1:1/v1 P2P_GRAPH_RAG_PROVIDER=cli REGENOLD_EXTERNAL_EMBEDDINGS=0 \
  .venv/Scripts/python.exe -m evals.regenold.runner_v2 --local --probe-oos --oos-suite all --label r318-oos

# zero-variance gold gate self-check (identity rule must show all-zero deltas)
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe .evalout/r317/sim_gate.py
```

Expected: the (b) table above, 255/255, 0 leaks, all-zero identity deltas.

---

### Step 1 — ADDITIVE-PASS ATTRIBUTION (cheapest untested, do this first)

**Why:** ~25 route passes ADD references. **Nobody has ever measured which one
contributes the most NON-GOLD refs.** Every R317 family tried to remove refs at
the end; none asked which pass put them there. This is the only untested cheap
direction and it is upstream of the whole problem.

**How:** each additive pass has an env gate. Toggle each one OFF individually
and score with the zero-variance instruments. Candidates (grep
`app/routes/regenold.py` for the add sites):
`_surface_anchor_citations`, `_add_prose_named_refs`, `_apply_role_duty_seed`
(`REGENOLD_ROLE_DUTY_SEED`), `boost_for_intent`, `_surface_prose_subpoints`,
`upgrade_references` (subpoint emitter), `_apply_assistant_anchor_inheritance`,
graph 2-hop (`REGENOLD_GRAPH_2HOP`), `REGENOLD_GRAPH_FUSE_SLACK`.

For a pass that is route post-processing you can simulate offline. For an
engine-level pass you need a real arm — use `easyhard_ab --local` with the
wrapper env, one pass per arm.

**Acceptance:** a pass whose removal cuts non-gold refs with **zero** gold loss
on both `sim_gate` and `holdout`. Then the full-476 gate (hard rule #7).

**Honest expectation:** several of these passes exist because an earlier round
measured them as recall-positive, so most will trade recall for precision and be
rejected. The value is the ATTRIBUTION MAP even if nothing ships — it tells the
next round where the 197 non-gold refs come from, which nobody currently knows.

---

### Step 2 — IMPROVE THE RANKER, then clamp (highest leverage)

**Why:** gold sits at **rank 0 on 63.5%** of rows and within **top-2 on 86%**.
A top-2 clamp buys Ref Strict +0.031 and Ref Conciseness +0.156 — but costs
Ref Loose −0.083 today, which the recall guard (hard rule #8) rejects.

**If rank-0 accuracy reached ~85%, a top-2 clamp becomes nearly free.** That is
a RETRIEVAL improvement, not a trim, and it is the single highest-leverage
untested direction. It also directly closes the frontier gap: their advantage is
exactly that they emit a tighter, better-ordered set (2.59 refs, Ref Strict
0.6938).

Concrete sub-steps:
1. Measure current rank-0 accuracy per question shape — where is the ranker
   worst? (classification vs obligation vs procedure).
2. Known usable ranking signals, already measured:
   * a ref named in the **answer's lead sentence** is gold **79%** vs 35%
     otherwise (**2.26x lift**), captures 40% of gold — a strong RE-RANK
     feature, and a strong protection signal, but never a keep-list;
   * question-named heads (already used by `_prune_non_anchor_refs`);
   * `entity_extractor` role/concept boosts (R81-N.1, 3.0x/2.0x).
3. Re-rank, THEN re-measure the top-k curve in `sim_gate`. Ship a clamp only if
   the new curve shows top-2/top-3 at **zero** gold loss.

**Trap:** do not ship the clamp and the re-rank together. Measure the re-rank's
effect on the rank-0 curve FIRST; the clamp is only justified once the curve
moves.

---

### Step 3 — re-measure SOTA and decide

```bash
# fresh OURS arm — Stage-2 MUST be firing (p50 ~26s; if you see 0.1s it is the
# deterministic path and the arm is worthless for this comparison)
OPENAI_API_BASE=http://127.0.0.1:8000/v1 OPENAI_API_KEY=dummy P2P_GRAPH_RAG_PROVIDER=openai_wrapper \
  .venv/Scripts/python.exe -m evals.harness.easyhard_ab --local --label r318-ours

# frontier arm (resumable; re-run the same --label to continue a killed run)
.venv/Scripts/python.exe -m evals.harness.frontier_baseline \
  --model claude-opus-5 --label r318-frontier

.venv/Scripts/python.exe -m evals.harness.frontier_baseline --compare \
  --ours   evals/bench/results/easyhard-r318-ours-A.ckpt.jsonl \
  --theirs evals/bench/results/frontier-r318-frontier.ckpt.jsonl
```

**SOTA is declared when we win or tie all four axes.** Today we win 2 (Ref
Loose, kw recall) and lose 2 (Ref Strict, Ref Conciseness). Closing the
over-citation gap flips both losers — that single fix makes us SOTA on this
measurement.

⚠ NEVER run two wrapper-bound jobs concurrently. Run these sequentially.

---

### Step 4 — the official-scorecard axis (separate problem, do not skip)

Steps 1-3 target references. The official gap is **also** answer-side
(`AnsL − RefL = −13.1`). These are different problems and the frontier kw-recall
win does not resolve the official one. If reference work saturates, the
answer-side lever is the LLM-judge failure profile: omission-dominant
(`omission_rows 24` vs `fabrication_rows 5`, mean factual score 0.9647 against a
0.48 answer pass rate — accurate but INCOMPLETE).

⚠ Any answer-length change must be measured against Answer-Conciseness, the one
axis we lead. R307 measured that uncapping buys +0.0200 davidath Ans Strict with
**Ans Loose flat** — that is metric-gaming (Strict is recall and rises with
length), not quality. Do not chase it.

---

## 3. Gate stack for anything that touches references (R317, in order)

Each of these caught a DISTINCT real defect in R317. Do not skip one because an
earlier one was green.

1. `.evalout/r317/sim_gate.py` — zero-variance gold gate. **Bar: gold_dropped == 0.**
2. `.evalout/r317/holdout.py` — independent judged hold-out. **Bar:
   governing_dropped == 0.** Keep `usable_runs()` (hard rule #9).
3. davidath **FULL 476** — never `--qa-only` (hard rule #7).
4. 276-runner + OOS probe.
5. `evals.harness.easyhard_ab` — gold-bearing live A/B, last.

---

## 4. Traps that have already cost this project time

* **`--qa-only` is not a gate for a reference change.** QA gold is
  single-article and cannot show a chain-dropping defect (R317: 0 on QA, 67 on
  scenarios).
* **ABSENT IS NOT ZERO.** Pre-R302 judged runs emit `wrong_refs: []` even when
  the `failure_mode` names the over-citation. That trap invented **67 phantom
  regressions** in R317. Usable runs: `grounded-r302-*`, `grounded-r304-*`,
  `grounded-lawstronaut-*`.
* **Never live-A/B a pure reference transform.** Two runs with an IDENTICAL
  baseline arm changed 20/40 rows' `pred_refs` and sign-flipped all three ref
  axes on generation variance alone (R288). Replay a recorded arm.
* **A hand-tuned classifier is not a rule.** R317's ask-type rule looked clean
  only under its author's own shape classifier; an independent implementation
  disagreed on 30% of rows and flipped the safety verdict.
* **`/v1/auth/status` lies.** Verify the wrapper with a real POST.
* **`easyhard_ab --local` silently runs deterministic** unless the wrapper env
  is set — p50 0.1 s instead of ~26 s.
* **railway.toml `[deploy.envs]` has NEVER applied** — Railway's `[deploy]`
  schema has no `envs` key. Bake config as CODE defaults.
* **git-worktree baselines have no `.env`** — full-suite failure diffs must be
  run IN PLACE (a worktree baseline manufactured 30 phantom regressions on the
  same commit).

---

## 5. Instruments (reuse, do not rebuild)

| tool | purpose |
| --- | --- |
| `.evalout/r317/sim_gate.py` | zero-variance gold gate over a recorded arm |
| `.evalout/r317/holdout.py` | independent judged hold-out + `usable_runs()` |
| `.evalout/r317/run_candidate.py` | one-call measure of a candidate rule |
| `evals/harness/frontier_baseline.py` | **committed** frontier arm + `--compare` |
| `evals/harness/easyhard_ab.py` | gold-bearing live A/B (count-ratio conciseness) |
| `evals/judge/grounded.py` | Sonnet-5 judge vs verbatim Act text (no gold needed) |

Recorded arms worth reusing: `easyhard-r282-fullprod-clean-A.ckpt.jsonl` (132
rows, gold-bearing, the sim_gate default), `easyhard-r317-oursS2-A.ckpt.jsonl`
(fresh current code, Stage-2), `frontier-r317-frontier-opus5.ckpt.jsonl`.

---

## 6. Current repo state at handoff

* `_apply_tier_exclusivity` + `_r317_verdict` in `app/routes/regenold.py`,
  gated `REGENOLD_TIER_EXCLUSIVITY` **default OFF** (no-op in production).
* `tests/test_r317_tier_exclusivity.py` + `tests/test_r317_annex_iii_infra_guard.py`
  — 57 tests, green.
* `evals/harness/frontier_baseline.py` — new, committed.
* CLAUDE.md — hard rules 7-9 added, Validation policy extended with the
  reference gate stack, "Fresh session plug-in" rewritten to current state,
  R317 round entry + scorecard row added.
* Uncommitted and NOT mine (concurrent work, leave alone):
  `docs/partners/regenold/LIFECYCLE_*.md`, `scripts/lifecycle_demo/`, `uv.lock`.
