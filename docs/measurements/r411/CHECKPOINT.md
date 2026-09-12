# R411 — checkpoint

**As of:** 2026-09-12
**Branch:** `fix/r409-r408-audit`
**Base:** `dd797d9a9de6` (production)
**Status:** fixes implemented + unit-tested; full suite **7886 passed / 2 skipped**;
significant samples COMPLETE (both splits); full release gate DEFERRED by operator
instruction ("full gate only when all has been optimised and fixed").

> **THE HEADLINE RESULT.** `REGENOLD_STAGE2_FULL_SYSTEM` looked like a clean win on a
> 12-row easy probe (+13.03 pp Speed, `gold_drop_hd` +0) and **FAILS** on the graded hard
> split (`gold_drop_hd` 12 → 18, `ref_loose` −10.81 pp). Default stays OFF. See §2.3.
> This is the whole reason to run a significant sample on the graded modality rather than
> the convenient one.

---

## 1. What is implemented on disk

| change | file | state |
| :--- | :--- | :--- |
| `REGENOLD_STAGE2_FULL_SYSTEM` default flipped to **ON** (deny-list) | `app/engines/_graph_rag_impl.py` | done, 18 tests green |
| `_detect_reclassification_inquiry` trailing-ask guard | `app/engines/_graph_rag_impl.py` | done, corpus-neutral (22/110 unchanged) |
| regression tests | `tests/test_r411_stage2_full_system.py`, `tests/test_r411_detector_precision.py` | 18 passed |
| detector-precision instrument | `docs/measurements/r411/intercept_precision_audit.py` | done |
| per-arm latency instrument | `docs/measurements/r411/ab_latency_report.py` | done |
| architecture audit + roadmap | `docs/reviews/r411-architecture-audit.md` | done |

## 2. Evidence captured so far

### 2.1 Paired probe, easy split, n=12 (COMPLETE)

`evals.harness.easyhard_ab --local --multiturn skip --limit 12`
baseline `REGENOLD_STAGE2_FULL_SYSTEM=0` vs branch `=1`, live cloudflared tunnel,
0 errors in either arm.

| metric | A baseline | B branch | delta |
| :--- | ---: | ---: | ---: |
| latency mean | 27.98 s | 14.95 s | **−13.03 s** |
| latency p50 | 24.03 s | 13.90 s | −10.14 s |
| latency max | 52.29 s | 24.57 s | −27.71 s |
| **resp_speed** | 72.02 | **85.05** | **+13.03 pp** |
| answer chars | 2798.83 | 1179.67 | −58 % |
| paired rows faster | — | 12 / 12 | 0 slower |

Official reference axes from the same run:
`ref_loose 0.9583 → 0.9583`, `ref_strict 0.4583 → 0.4768`,
`ref_conc 0.2514 → 0.2540`, `kw_recall 0.9444 → 0.9444`,
**`gold_drop_hd` 1 → 1 (+0, passes hard rule #8)**.

Artifacts: `score-r411-fullsys-probe-n12.json`, `ckpt-r411-probe-n12-arm{A,B}.jsonl`,
`latency-ledger-fullsys-easy.md`.

### 2.2 Aborted full-corpus run, arm A n=40 (preserved)

`ckpt-r411-fullsys-aborted-full-armA.jsonl` — 40 baseline rows at a mean latency
**29.66 s**, i.e. the baseline arm independently reproduces the production
`resp_speed ≈ 71.65` read. Kept because it is the only large baseline sample on disk;
do not use it as a paired statistic (its branch arm was never run).

### 2.3 Significant sample, hard split, n=37 (COMPLETE — THE LEVER FAILS)

`evals.harness.easyhard_ab --local --multiturn only` — the graded modality (multi-turn
plus adversarial pushback). Both arms 37/37, 0 errors.

```
HARD n=37      baseline   branch    delta
ref_loose       0.8423    0.7342   -0.1081   GOLD LOSS
ref_strict      0.4392    0.3932   -0.0461
ref_conc        0.1719    0.2391   +0.0672
kw_recall       0.7793    0.7432   -0.0360
pred:gold       2.74      2.59     -0.16
gold_drop_hd    12        18       +6        ** FAILS hard rule #8 **
lat p50 s       31.2      21.5     -9.7
```

Per-arm latency (`ab_latency_report.py easyhard-r411-fullsys-hard`): mean
**32.52 s → 21.50 s**, `resp_speed` **67.48 → 78.50 (+11.02 pp)**, 33 of 37 rows faster,
answer chars 2884 → 1322.

The speed win is real and large; the correctness cost is larger. `+13 pp Speed` is worth
`×1.182^(1/8) = +1.65 pp` Overall and `-10.81 pp ref_loose` is not bought back by it.
Artifacts: `score-r411-fullsys-hard-n37.json`, `ckpt-r411-hard-arm{A,B}.jsonl`,
`latency-ledger-fullsys-hard.md`.

### 2.4 Expert-review grounding fixes (statutory, corpus-verified)

Sourced from `Antifragile AI expert review.txt`, verified against our OWN statutory
corpus rather than against a paraphrase:

* **Art. 6(3) vs 6(4).** The live prompt attributed the Art. 49(2) documentation and
  registration duty to Article 6(3). The statute puts it in **Article 6(4)**. Fixed in
  `app/data/graph_rag_prompt_templates.py`; pinned by
  `tests/test_r411_expert_review_grounding.py`.
* **Art. 5(1)(c) social scoring.** `PROPORTIONALITY[0]` still said "social scoring by
  public authorities" — a Commission-proposal limitation removed from the final
  Regulation, and already forbidden by our own prompt rule. Also corrected the
  Annex III tier's misplacement of the significant-risk test in Art. 6(2) and its
  missing Art. 6(4). **Provenance note: `PROPORTIONALITY` has NO reader anywhere in
  `app/`, so this is latent-trap maintenance, not a live-behaviour fix.** Do not claim
  a metric gain for it.
* Checked and found already-correct (no change): social-scoring prose elsewhere,
  Annex III 5(a) "by public authorities", the Art. 6(3) profiling override, and the
  Recital 27 / Art. 95(2)(a) guiding-principles answer.

## 3. How to resume

```bash
# per-arm latency from whatever checkpoints exist (safe to run at any time)
.venv/Scripts/python.exe docs/measurements/r411/ab_latency_report.py easyhard-r411-fullsys-hard

# the hard sample, if it needs re-running
.venv/Scripts/python.exe -m evals.harness.easyhard_ab --local \
  --label r411-fullsys-hard --multiturn only \
  --baseline-env REGENOLD_STAGE2_FULL_SYSTEM=0 \
  --branch-env REGENOLD_STAGE2_FULL_SYSTEM=1

# THE DEFERRED FULL GATE — run only once every lever is in (operator instruction)
.venv/Scripts/python.exe -m evals.harness.easyhard_ab --local \
  --label r411-release-gate \
  --baseline-env REGENOLD_STAGE2_FULL_SYSTEM=0 \
  --branch-env REGENOLD_STAGE2_FULL_SYSTEM=1
```

`--local` is required for an env-flip A/B (the deployed service's env cannot be
changed per-arm). It still dials the live cloudflared tunnel, so it measures the
real transport.

## 3.1 Ship record

* **PR #413** merged to `main` as `f7b1250933d5e4dc6306713bee616f7a7de6af`; both CI gates
  green on a clean clone (Deployable 38 s, Test suite 2 m 04 s).
* **Production live on `f7b1250933d5`**, `/healthz` `status: ok`.
* Live verification on the deployed endpoint (real Opus via the cloudflared tunnel):
  * *"Are AI systems for social scoring prohibited ... and is the prohibition limited to
    public authorities?"* → **"Yes ... and no, the prohibition is not limited to public
    authorities"**, wire refs `['Article 5.1.c']`.
  * *"If a provider relies on the Article 6(3) derogation for an Annex III system, what
    documentation and registration duties apply?"* → names **Article 6(4)** and
    **Article 49(2)**, wire refs `['Article 49.2', 'Article 6.3', 'Article 113.3']`.
    Note: `Article 113.3` (application dates) is off-topic here — a small over-citation on
    the deterministic intercept path, recorded rather than hidden.

## 4. Do not lose this

* `REGENOLD_STAGE2_FULL_SYSTEM` **is** registered in `_engine_cache_key`
  (`app/routes/regenold.py`), so the two arms cannot share a cached engine output.
  The harness's standing "latency is confounded by a shared cache" caveat does not
  apply to this pair; the effect is also 12/12 per-row consistent.
* The R282 veto on forwarding `ANSWER_GENERATE_SYSTEM` to the system slot
  (`kw_recall −0.267`) **does not reproduce** on the current stack: measured flat at
  0.9444 in both arms. The veto's text is preserved in the code comment rather than
  deleted, so the history is not lost.
* `easyhard_ab` scores the **reference** axes only. Ans Correctness (loose/strict)
  needs the grounded judge (`ab_judge`); it has **not** been read for this lever.

---

## 5. Continued work — detector precision, recall accounting, ref minimality

### 5.1 The Article 6(3) intercept was keyed on a MENTION, and the "mention" test was dead

`_is_curated_authoritative_intercept` short-circuits Stage-2 and ships a STOCK
curated verdict, so a detector that fires on a provision *mention* answers a question
that was not asked. Measured over 33 detectors x 15 carriers x 3 refs
(`docs/measurements/r411/mention_vs_ask_probe.py`): **only `_detect_article_6_3_inquiry`
was mention-keyed.** Live effect: *"If a provider relies on the Article 6(3) derogation
for an Annex III system, what documentation and registration duties apply?"* was answered
with the `rg_031` classification verdict.

**Two defects, not one.**

1. The bare-designation alternative ended in `\b`. The designation ends in `)`, a
   non-word char, so `\b` can never match when followed by a space — the alternative was
   **DEAD** for the ordinary form ("Article 6(3) derogation") and only matched when glued
   to a word ("6(3)a"). So the probe's first reading of "zero mention fires" was a broken
   regex, not a working gate. Now a `(?![0-9a-zA-Z])` lookahead; pinned by
   `test_designation_regex_is_not_dead`.
2. With the regex fixed, the gate needs a real ask-test. Final rule, all three parts
   measured:
   * **topic cue** — risk-classification vocabulary OR the exception's own name
     (exception / exemption / exempt / derogation / self-assessment / preparatory task).
     A neutral ask ("what does Article 6(3) say?", "please summarise Article 6(3)")
     carries neither and does not fire.
   * **premise veto** — a designation inside a comma-terminated conditional protasis is a
     PREMISE, not the ask ("**If** a provider relies on the Article 6(3) derogation, what
     duties apply?"). Same principle as the R411 trailing-ask guard on
     `_detect_reclassification_inquiry`: the ask decides.
   * the veto and the gate are scoped to the **bare designation only** — a question that
     names the *exception* is already asking about it.

Result: probe **33/33 ask-keyed, 0 mention-keyed**; the whole official corpus is unchanged
at **22/110, same rows**; and the pre-existing `TestArticle63Routing` contract (5 rows)
plus its deterministic-answer test are green again. An intermediate cut that gated the
exception *phrases* too was caught by that suite and reverted — recorded so the narrowing
is not re-attempted.

### 5.2 Member-guard recall: the residual is NOT reachable without re-buying the loss

`docs/measurements/r411/member_recall_probe.py` replays the closed-set member detector
over the 12 distinct rows carrying the 22 `OMITTED_ENUMERATED_ITEM` criteria and reports
WHICH gate blocks each:

| blocker | rows |
| :--- | ---: |
| `is_list_question` false | **7** |
| no closed-set head discovered (topical head, e.g. "instructions for use") | 3 |
| answer never names the set (`_prefix_closure`) | 2 |

Read against the criteria themselves, the 7 "not a list question" rows are mostly the
WRONG INSTRUMENT, not a recall gap: `rg_010` wants the provider/deployer attribution of
Art. 14(3) measures, `rg_014` wants the full text of a single Annex III point,
`rg_078` and `rg_102` are clause/limb fidelity on yes/no asks. Only `rg_051` (Art 22(3)),
`rg_059` (Art 68(3)) and `rg_094` (Annex XII.1) are genuine lettered sets the answer
touched partially — and each of those would ALSO need `_question_engages` to admit a
question that does not ask for the set, i.e. the citation-side rule that lost gold in
R409 §6.8. **Conclusion: the member detector is at its safe recall ceiling.** The
instrument for these rows is the evidence/prompt layer (put the full provision text in
front of Stage-2), not a wider engagement rule. No change made — deliberately.

### 5.3 Ref Conciseness (55.93): the prune FAILS its own safety test

`docs/measurements/r411/ref_minimality_probe.py`, over the 107 ref-scored rows of the
frozen R407 hard ledger:

```
emitted refs                 : 301
  in expected key            :  80
  EXCESS                     : 221 (73.4 %)
    excess, head cited in prose   : 202
    excess, head ABSENT from prose:  19   <- the only prunable set
rows that would shed >= 1 ref :  13
expected refs present         :  80
  ...head ABSENT from prose    :   2   <- UNSAFE
expected refs absent           :  55   (the ref_loose recall gap)
```

The obvious prune — "drop any emitted ref the prose never mentions" — is meant to be
reference-neutral by construction, and it is **not**: `rg_019` (Article 3.60) and
`rg_076` (Article 3.2) are correct definitional answers that quote the definition TEXT
without naming the provision. Pruning would delete two expected refs to shed 19 excess
ones: a ref-CORRECTNESS loss traded for a conciseness gain, which is precisely the trade
hard rule #8 exists to refuse.

The deeper reading is the useful part: **91 % of the excess (202 of 221) is content the
answer actually discusses.** Ref Conciseness is not measuring noise here, it is
penalising thoroughness — the expected key is the *minimal* set, and the engine answers
with the surrounding framework (Art 5, 50, 51-56, Annex III) because that is the honest
answer to the question. Which is why three previous minimality attempts failed, and why
the axis should be moved generation-side (discuss fewer provisions) rather than pruned
post hoc. No change made.

### 5.4 The single-turn full-system gate is implemented but **VOID** — do not read it

`REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN` is implemented (§5.5) and 21 tests pass. The
paired easy-split gate (95 rows, both arms) was launched and **stopped after 2 rows as
invalid**:

```
graph_rag.openai_wrapper_provider_outage — Stage-2 LLM path is DOWN ...
api_status_500: {"error":{"message":"No response from Claude Code", ...}}
graph_rag.bedrock_auto_fallback — Cloudflare wrapper failed ... Attempting AWS Bedrock synthesis.
```

The Claude-Max wrapper is up but its bundled Claude Code CLI is not (expired OAuth), so
Stage-2 is served by the Bedrock auto-fallback — and `_bedrock_complete_for_graph_rag`
receives `system=system` (the full prompt) unconditionally; `wrapper_system` is only ever
built inside `_openai_wrapper_complete_for_graph_rag` (`system=wrapper_system` at the
wrapper call, the persona substitution). The flag under test rewrites the WRAPPER leg
only, so with the wrapper down **both arms are byte-identical by construction** and the
run can only measure Stage-2 sampling noise. The check that catches this is one line: is
the primary leg actually serving? If `bedrock_auto_fallback` appears in the log, the A/B
is void.

To run it: re-seed the wrapper's OAuth token (`login.bat`) and verify with the curl in
the outage message, then:

```bash
.venv/Scripts/python.exe -m evals.harness.easyhard_ab --local \
  --label r411-fullsys-singleturn-easy --multiturn skip \
  --baseline-env REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN=0 \
  --branch-env   REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN=1
```

### 5.5 What §5 shipped

| change | file | state |
| :--- | :--- | :--- |
| Art 6(3) designation regex un-deadened + topic cue + premise veto | `app/engines/_graph_rag_impl.py` | done, corpus-neutral (22/110 same rows) |
| `REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN` (default OFF) | `app/engines/_graph_rag_impl.py` | done |
| `history_turn_count` param + `_engine_cache_key` registration | `app/engines/_graph_rag_impl.py`, `app/routes/regenold.py` | done |
| tests | `tests/test_r411_mention_vs_ask.py`, `tests/test_r411_stage2_full_system.py` | 21 + 12 pass |
| instruments | `docs/measurements/r411/{member_recall_probe,ref_minimality_probe,live_prod_check}.py` | done |

### 5.6 Ship record and live verification (this round)

* **PR #415** merged to `main` as `7bf45da`; both CI gates green on a clean clone
  (Deployable 37 s, Test suite 2 m 33 s). Full suite **7922 passed / 2 skipped**.
* **Production live on `7bf45dac1239`**, `/healthz` `status: ok`.
* `docs/measurements/r411/live_prod_check.py` — **ALL CHECKS PASSED**:

  | case | before (previous deploy) | after |
  | :--- | :--- | :--- |
  | *"If a provider relies on the Article 6(3) derogation for an Annex III system, what documentation and registration duties apply?"* | the `rg_031` classification verdict; refs `['Article 49.2', 'Article 6.3', 'Article 113.3']` | **not** the verdict; refs `['Article 6.3', 'Annex III.7.c', 'Article 5.1.d', 'Annex I']` — **Art 113.3 gone** |
  | *"Is an AI system used to structure or deduplicate information for an Annex III use case considered high-risk?"* | verdict (correct) | verdict (correct), refs `['Article 6.3.a', 'Article 49.2', 'Annex III.7.b']` — **intercept recall intact** |

* **RESIDUAL, recorded rather than hidden.** The duties question now falls through to the
  normal path, and that path answers with the Article 6(1)/6(2) classification routes —
  naming neither Article 6(4) nor Article 49(2), the duties actually asked about. That is
  **out of scope for the mention gate** (the gate's guarantee is that a mention no longer
  hijacks Stage-2, which it now meets) but it is a real relevance gap in the fallback
  path and belongs on the next round's list. Also note the probe's first cut asserted the
  verdict on the phrase "not considered high-risk"; the live wording is "is not
  high-risk", so it reported a false failure of the intercept's own recall. Assert the
  phrase the verdict actually uses.
