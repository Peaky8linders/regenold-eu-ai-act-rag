# R288 — CHECKPOINT / fresh-session handoff

**Date:** 2026-07-24. **Status:** R288 merged as **#298** (`62ca878`), deployed
(`/healthz` → `commit: 62ca8786d6bb`), **gate default-OFF so inert on the wire**.
R288.1 review fixes on branch `r288.1-review-fixes` — see §1.

**Two jobs left:** (A) finish R288 with a properly-powered A/B, (B) run + judge the
HARD official batch, which has **never been graded by our own instrument**.

> **§1 and §2 were rewritten on 2026-07-24 after a post-merge adversarial review.**
> The original §2d asserted two things about the shipped code that were **false**,
> and one of them made Job A's prescribed experiment impossible. If you read an
> older copy of this file, discard §2d and §3 from it.

---

## 0. Read these first (5 min, saves hours)

* `CLAUDE.md` hard rule #6 — `evals.harness.ab_judge` / gold-bearing A/B is the
  merge gate, davidath is a REGRESSION GUARD ONLY.
* Memory: `project_easyhard_ab_noise_floor_n40.md` ← **the most important prior
  finding. Read before designing any A/B.**
* Memory: `project_nli_verifier_measured_dead.md` — do not revisit NLI/torch.
* Memory: `project_ans_metrics_not_comparable.md` — never compare a local Ans
  number to the regenold report.
* **§1.1 below — the two recorded A/B runs are confounded. Do not reuse them.**

---

## 1. State

R288 is **merged and deployed**. `main` = `62ca878` = PR #298, and the production
`/healthz` reports that same commit. The gate (`REGENOLD_GROUNDING_TEXT`) defaults
to `0`, so the wire behaviour is unchanged.

The R288.1 review fixes live on **`r288.1-review-fixes`** (branched from
`origin/main`, worktree `.claude/worktrees/r288-1-review-fixes/`). They are
gate-ON-only corrections plus one latent bug; nothing changes default behaviour.

⚠ **Railway auto-deploys `main`,** and per `project_multiagent_autocommit_env.md`
automation in this environment has auto-committed `main` mid-session before — it
did so again during the R288.1 session (a parallel agent branched, committed,
opened #298 and merged it while the review was running). Do not `git add -A`; the
repo root is littered with `_v_*.py` / `_r_*.py` scratch files that predate this.
Work in a worktree.

Also still installed locally: **torch + transformers + sentence-transformers**
(~2.5 GB in `.venv`). Harmless (the only import is behind the default-OFF NLI
path; OOS probe verified 21/21), but the deploy is torch-free — uninstall if you
want local/prod parity.

### 1.1 ⚠ The two recorded A/B runs are CONFOUNDED — do not reuse them

`easyhard-r288-arm1-ab.json` and `easyhard-r288-arm1-tight.json` were both run
against the **pre-R288.1** engine, in which turning the gate ON also **widened the
R113 hallucination guard's allowlist** (§2g). Their branch arm therefore measured
*"verbatim grounding **and** a weaker citation guard"* as one treatment. The
reference axes in those files cannot be attributed to grounding.

The signature is visible in the numbers: `ref_loose` **0.858 → 0.875** (up — the
guard dropped fewer citations) with `ref_conc` **0.406 → 0.347** (down sharply —
more of the surviving citations were off-target). That is what a loosened filter
looks like, and it is exactly what a genuine grounding win should *not* look like.

`kw_recall` (+0.075 / +0.108, the one stable signal) is measured on **answer
text**, not on citations, so it is the least affected by the confound — but it is
not clean either, since the guard can drop a whole polish. **Re-baseline both arms
on `r288.1-review-fixes` before drawing any conclusion.**

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

### 2d. Arm 1 is BUILT and gated OFF *(corrected 2026-07-24)*
`_render_grounding_text()` fetches the question-relevant **verbatim paragraphs of
the CITED refs** via `provision_text.select_relevant_paragraphs`.
Env: `REGENOLD_GROUNDING_TEXT` (default `0`), `REGENOLD_GROUNDING_REF_CHARS`
(default 1200, clamped 200-4000).

> **The original wording of this section was wrong in two ways.** It said "Both
> are in `_engine_cache_key`" — only the master gate was; `REGENOLD_GROUNDING_REF_CHARS`
> was absent, and a **phantom** `REGENOLD_GROUNDING_SCOPE_ALL` (read nowhere in the
> codebase, a leftover of the abandoned Arm 0) sat in its place. The same false
> claim appears in #298's commit message and in the code comment. It said "BOTH
> block call sites" — there are **three** in production (`graph_rag.py:6155`,
> `graph_rag.py:6415`, `logic_rag.py:415`). Fixed on `r288.1-review-fixes`.

### 2e. Gates green for Arm 1 — and what they do NOT cover
davidath QA gate-OFF **byte-identical** (Ans Strict 0.4037 / Ref Loose 0.8394 /
Ref Strict 0.5543 / Ref Conc 0.4395 / Tone 1.0) · 276-runner **255/255** ·
OOS **21/21, 0 leaks** · `tests/test_r288_grounding_text.py` **30/30** (24 from
#298 + 6 from R288.1) · touched-surface **zero regressions** (stash A/B; the 12
`_when_wrapper_enabled` failures are pre-existing under `provider=cli`).

⚠ **Every one of those gates ran with the gate OFF.** They say nothing about
gate-ON behaviour — which is precisely where both R288.1 defects lived. Do not
read "all gates green" as "the arm is validated". The arm has never been
validated; that is Job A.

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

### 2g. What the post-merge review found *(new, 2026-07-24)*

Six blind lens reviewers over the merged diff, each finding then sent to an
independent skeptic instructed to refute it. **20 findings filed, 20 survived** —
a 100% survival rate is itself weak evidence that the skeptics were not skeptical
enough, so the three load-bearing ones below were re-verified by hand, and one
panel severity was overridden downward.

Fixed on `r288.1-review-fixes` (all injection-tested — revert the fix, the named
test fails):

| # | Defect | Consequence |
|---|---|---|
| 1 | **The gate widened the R113 hallucination allowlist** (§2g) | Confounded both recorded A/Bs |
| 2 | **`REGENOLD_GROUNDING_REF_CHARS` not in `_engine_cache_key`** | Job A's budget sweep could not have worked |
| 3 | LogicRAG returned a question-less context | Latent — `REGENOLD_LOGIC_RAG` defaults off |

Panel called #3 "high"; downgraded to **latent** after checking
`graph_rag.py:7382` — the flag defaults off, so it is wrong-when-enabled, not
shipped-wrong.

Plus hygiene, none of which changes rendered output: Arm-0 → Arm-1 relabel at
three sites, dead `_GROUNDING_TAG_RE` removed, `provision_text` import hoisted out
of the per-ref loop, the "`_llm_generate_answer` has zero callers" docstring
corrected (it has one, in `tests/test_gemini_routing.py`), two silent
`except: pass` given a `logger.debug`.

### 2h. The guard-widening defect, in detail — *this is the one that matters*

`_extract_context_grounded_refs` (the R113 drift guard) calls
`_mine_refs_from_text` on the **rendered** references block to decide what the
Stage-2 polish is *allowed to cite*. Verbatim Act text is saturated with
cross-references, so rendering it into that block fed the guard provisions that
were **never retrieved**.

Reproduced on a 3-obligation context (Arts. 9 / 11 / 13):

```
gate OFF  grounded refs = 3   ['Art. 9', 'Art. 11', 'Art. 13']
gate ON   grounded refs = 6   [... + 'Art. 60', 'Art. 72', 'Annex IV']
```

Art. 60, Art. 72 and Annex IV became citable purely because the **bodies of the
cited articles name them** — while the block itself instructs the model "do NOT
cite anything not already listed above". The guard was being defeated by the text
the treatment introduced.

Fixed by rendering the section behind a marker and cutting it back off **for the
miner only**:
`_build_context_references_block(context, include_grounding=False)`. The Stage-2
prompt is **byte-for-byte unchanged** (still 3366 chars of verbatim text on that
context) — only the guard's view narrows.

**The first version of the regression test for this was a placebo.** It called
`_build_context_references_block(..., include_grounding=False)` directly, so it
asserted only that the mechanism *exists*; reverting the call site inside the
guard left all 29 tests green. It now calls the real entry point,
`_extract_context_grounded_refs`. There is also a **positive control** asserting
the verbatim text still *does* introduce cross-refs, so the guard test cannot pass
vacuously if the provision corpus ever stops resolving. **Injection-test anything
you add here — this suite has already produced one false green.**

---

## 3. JOB A — finish R288 with a powered A/B

**Goal:** decide ship / don't-ship on Arm 1 with a measurement that can actually
resolve it.

**PREREQUISITE — run this from `r288.1-review-fixes` (or after it merges), NOT
from `62ca878`.** On `62ca878` the branch arm also carries a loosened citation
guard (§1.1, §2g) and the budget sweep below is a no-op (§2d). Both are fixed on
that branch. Re-baseline; do not diff against the two archived runs.

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

**Then sweep the three treatment knobs.** All three change what the model sees;
none of them was ever varied in a valid run.

1. **Per-ref char budget** — the 1200-char default grew answers **+12%**, and
   Answer Conciseness is the ONE axis we lead (96.0 easy / 93.4 hard):
   `--branch-env "REGENOLD_GROUNDING_TEXT=1,REGENOLD_GROUNDING_REF_CHARS=500"`
   (try 300/500/800). ⚠ **This sweep holds the gate ON in both arms**, so before
   R288.1 both arms hashed to the same `_engine_cache_key` and arm B was served
   arm A's cached output — a guaranteed flat "no effect". Verify you are on the
   fixed branch: `pytest tests/test_r288_grounding_text.py -k ref_char_budget`.

2. **`_GROUNDING_MAX_REFS` (currently 3, `graph_rag.py`)** — *not env-gated; edit
   the constant.* `_context_article_refs` returns primaries first, then their
   cross-refs, so any question anchoring ≥3 primary articles exhausts the cap on
   primaries and grounds **zero cross-refs** — while easy answers cite 2.93-3.99
   refs. The 67%-of-refs-ungrounded defect R288 exists to fix is therefore only
   partly closed at the shipped setting. Deliberately left at 3 in R288.1 so the
   archived runs still describe *some* real configuration; raising it is a
   first-class experiment, not a bugfix.

3. **Annex/recital rows are paraphrase, not verbatim** — the second section of
   `_render_grounding_text` prints `entry['text']` from
   `referenced_annexes_and_recitals`, which for Annex entries is the KB summary
   stub, i.e. exactly the paraphrase R288 exists to replace. (The section header
   does *not* claim verbatim, so this is an under-delivery, not a mislabel — the
   review panel's phrasing on this point overstated it.) Routing those refs
   through `select_relevant_paragraphs` too is the obvious Arm 2.

**Decision gates:**
1. **KILL:** answer length rises materially across repeats → do not ship (AnsCon
   has zero headroom).
2. **KILL:** `ref_loose` (recall) drops consistently across repeats → R142.1.
3. **SHIP** only if `kw_recall` holds up AND length + recall are flat across
   repeats. Then also run the grounded judge on both arms (§4 pattern) to confirm
   `answer_correctness` moves, since `kw_recall` is only a proxy.

⚠ **Gate 2 needs re-reading post-R288.1.** Before the fix, a *rise* in `ref_loose`
was the expected artefact of the widened guard, so "recall drops" was the wrong
alarm to watch. With the guard restored, a recall drop now means what the gate
says it means. Interpret any pre-R288.1 `ref_loose` reading as uninformative.

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
  **R288 got this wrong and three documents said it got it right** (the commit
  message, this file's §2d, and the code comment). The doctrine is *"anything that
  changes engine output"*, not *"gates"* — a **numeric knob is not exempt**, and
  the trap only springs when the boolean gate is held EQUAL across arms, which is
  exactly the shape of a tuning sweep. When you add one, write the test that holds
  every other flag fixed and varies only the new one.
* **A cache-key entry for a var nothing reads is worse than no entry** — it reads
  as coverage. `REGENOLD_GROUNDING_SCOPE_ALL` sat in the tuple with a comment
  calling it "the scope-ablation knob"; it was never read anywhere. Grep any flag
  you find in that tuple before trusting it.
* **Anything rendered into the references block is also read by the R113 guard**
  (`_extract_context_grounded_refs` → `_mine_refs_from_text`). Adding text to that
  block therefore widens what the polish may cite. If your addition is
  *supporting* context, exclude it from the miner
  (`include_grounding=False` is the pattern) or you silently weaken the
  hallucination guard while measuring it as a win.
* **Injection-test every regression test you add to `test_r288_grounding_text.py`.**
  Revert your fix; if the suite stays green the test is a placebo. This has already
  happened once: a guard test that called the block builder directly instead of the
  guard passed 29/29 against fully-reverted code.
