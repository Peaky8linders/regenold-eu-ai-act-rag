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

**R411b — re-checked after the login was re-seeded (2026-09-12). The diagnosis CHANGED;
the lever is still blocked, for a different reason.**

What was re-verified, in order, so the block is not misattributed again:

| layer | state | evidence |
| :--- | :--- | :--- |
| DNS / Cloudflare edge | up | `nslookup` → Cloudflare A records |
| Cloudflare Access | up, token accepted | a bare `curl` returns the Access HTML challenge; with `CF-Access-Client-Id`/`-Secret` (both in `.env`) it reaches the app |
| wrapper process | up and healthy | `GET /health` → `{"status":"healthy",...}`; `GET /v1/models` lists models |
| wrapper host | **local** | `127.0.0.1:8000` answers identically to the tunnel; the tunnel just fronts this box |
| Claude login | **valid** | `~/.claude/.credentials.json` mtime `11:41`, `subscriptionType=max`, `rateLimitTier=default_claude_max_5x`, account `bacu.andrei@gmail.com` |
| Claude Max quota | **EXHAUSTED** | `claude -p` → *"You've hit your session limit · resets 2:10pm (Europe/Bucharest)"* — **account-wide**, identical on `claude-haiku-4-5` and the default Sonnet |

So every request through the wrapper returns `HTTP 500 {"error":{"message":"No response from Claude Code"}}`
for **all** models (opus-4-6, sonnet-4-6, sonnet-4-5, haiku-4-5 all tried). The login is
not the problem any more; the subscription window is.

**The unblock that exists, and why it is not mine to take.** The wrapper's own `.env`
(`D:/Claude Projects/claude-code-openai-wrapper/.env`) is configured:

```
CLAUDE_AUTH_METHOD=cli          # <- forces the Claude Code CLI / Max subscription
WRAPPER_FORWARD_SYSTEM_PROMPT=1 # <- the caller's system prompt IS forwarded, so the lever is meaningful
ANTHROPIC_API_KEY=SET(108)      # <- a working API key sits UNUSED
AWS_BEARER_TOKEN_BEDROCK=EMPTY
```

`CLAUDE_AUTH_METHOD=api_key` (or a second instance on another port with that override)
would bypass the Max window and use the API key that is already present — at per-token
API cost, on an account with `hasExtraUsageEnabled: false`. That is a billing decision on
a repo outside this project, so it is **escalated, not taken**.

The other fact worth recording: `WRAPPER_FORWARD_SYSTEM_PROMPT=1` confirms the wrapper does
not drop the system prompt, so the R383 persona cap in *our* code is the whole mechanism —
the lever is real, not inert for a second reason.

To run it once a working Stage-2 leg exists, verify the curl in the outage message
returns 200 first, then:

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

## 6. Re-validation record (2026-09-12, tunnel re-check round)

Everything that does **not** need the Claude-Max leg was re-run from a clean tree at
`9e59f8b` and reproduces the recorded readings exactly — no drift, so the numbers in §5
are still the current numbers:

| check | command | result | recorded | match |
| :--- | :--- | :--- | :--- | :--- |
| full suite | `pytest tests/ -q` | **7922 passed / 2 skipped** (228.7 s) | 7922 / 2 | ✅ |
| mention-vs-ask | `mention_vs_ask_probe.py` | **33/33 ask-keyed, 0 mention-keyed** | 33/33 | ✅ |
| member recall | `member_recall_probe.py` | blockers **7 / 3 / 2** | 7 / 3 / 2 | ✅ |
| ref minimality | `ref_minimality_probe.py` | **221 excess (73.4 %)**, 19 prose-absent, **2 expected refs prose-absent → UNSAFE** | same | ✅ |
| corpus neutrality | `intercept_precision_audit.py` | each detector **1/110**, total **22** | 22/110 | ✅ |
| production live | `live_prod_check.py` | **ALL CHECKS PASSED** on `2031219ba476` | passed | ✅ |

The single item that **could not** be re-run is the `REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN`
paired easy-split gate, blocked by the Max session window (§5.4). Nothing else in this
round is outstanding — the deterministic surface is green end to end.

## 7. Re-opened judge reports — the four fixes (2026-09-12)

**Method.** The R409 frontier-judge instrument was re-run verbatim against the current
engine (`rejudge_open_issues.py`), then re-judged with the SAME judge, SAME prompt,
SAME temperature as the R409 snapshot (OpenRouter `anthropic/claude-sonnet-5` @ 0.1)
(`rejudge_current_answers.py`). 11 of 28 rows had changed answers since `dd797d9`, so
the recorded verdicts were stale; the re-judge produced the true open-issue list.

**Result on the 28-question expert-review set:**

| | R409 snapshot | after these fixes |
| :--- | ---: | ---: |
| strict (all criteria) | 5/28 = 17.9% | **11/28 = 39.3%** |
| loose (criteria mean) | 47.98% | **66.73%** (+18.75 pp) |
| tone pass | 21/28 | 22/28 |

Per-row deltas (vs the R409 snapshot): `part1_q03` 0.00 -> 1.00, `part2_q02` 0.00 -> 1.00,
`part2_q06` 0.00 -> 0.75, `part1_q15` 0.00 -> 0.75, `part2_q01` 0.33 -> 1.00,
`part1_q07` 0.50 -> 1.00, `part2_q05` 0.75 -> 1.00, `part1_q04` +0.25, `part1_q13` +0.25,
`part1_q16` +0.25, `part2_q04` +0.25, `part2_q11` +0.33. No row regressed against the
pre-fix R411 run.

### The four defects

| # | defect | file | evidence |
| :- | :--- | :--- | :--- |
| 1 | An explicit definition ask whose Art. 3 lookup MISSES fell through to the generic BM25 sentence walk, shipping one arbitrary statute sentence instead of the composed prose | `app/routes/regenold.py` (`_explicit_definition_ask`) | "What is the definition of high risk?" shipped Art. 6(2) verbatim (0/4); the EU-wording variant shipped Art. 6(6) (0/5). Same class on corpus `rg_048` |
| 2 | `_HOSPITAL_DEPLOYER_RE`'s three lookaheads matched anywhere, so a PROVIDER question naming a hospital as a VENUE was captured and Stage-2 short-circuited | `app/engines/_graph_rag_impl.py` | provider chatbot on a hospital website got the hospital-deployer roster (0/4) |
| 3 | The general verdict's confident "not among the practices prohibited under Article 5" is unsound for a DESCRIBED practice | `app/engines/_graph_rag_impl.py` + `app/engines/prohibited_gatekeeper.py` | clinical-trial triage variants lose the Art 5(1)(g) branch |
| 4 | The Art 50(1) information intercept's second key was a literal substring that excluded the indefinite article, so the STATUTORY phrasing missed | `app/engines/_graph_rag_impl.py` | "how must a natural person be informed that they are interacting with AN AI system?" shipped the Art 14(5) two-person rule (0/4) |

### The fix that had to be reverted

Fix 3's first cut swapped the wording for EVERY described practice. That silently disabled
the route's R376 prohibition-contradiction guard — measured, the race-inference variant
lost its correct Article 5(1)(g) verdict (loose 0.25 -> 0.00). Two changes were needed:
the denial grammar now tolerates the intervening adverb
(`prohibited_gatekeeper._PROHIBITION_DENIAL_RES`), and the wording swap is now scoped to
questions the prohibition gatekeeper did **not** match (`_prohibition_gatekeeper_matched`),
so R376 keeps owning every row it matched. Pinned by
`tests/test_r411_judge_reopen_fixes.py` and `tests/test_r376_prohibition_contradiction.py`.

### Corpus neutrality (hard rule #8)

Measured with the new `docs/measurements/r411/corpus_ab.py` (one clean subprocess per arm,
limiter disabled, real route, deterministic offline transport):

| flag | rows changed | ref_loose | ref_strict | ref_conc | expected heads lost / gained |
| :--- | ---: | ---: | ---: | ---: | --- |
| `REGENOLD_GENERAL_VERDICT_ART5_CONDITIONAL` 0 -> 1 | 1/110 (`rg_007`) | same | same | same | **0 / 0** |
| `REGENOLD_USER_INFORMATION_RECALL` 0 -> 1 | 0/110 | same | same | same | **0 / 0** |
| `REGENOLD_GENERAL_VERDICT_V2` 0 -> 1 | 5/110 | same | same | same | **0 / 0** |
| `intercept_precision_audit` whole gate | unchanged at 22/110, same rows | | | | |

Suite: **7962 passed / 2 skipped** (40 new pins). Ruff clean on every file this round
touched.

### Residuals (recorded, not hidden)

* **`part1_q12` / `part2_q08`** — the conditional clinical-trial question is still below its
  R409 reading (0.60 -> 0.20 / 0.00). Fix 3 removed the *wrong* negative, but the answer
  still lacks the branched Art 5(1)(g) / Annex III 1(b) / Annex I structure the criteria
  require. This regression pre-dates this round; the fix is a purpose-built branched answer,
  which needs its own gate.
* **`rg_066`** — "what is the EU database for high-risk AI systems ..." still ships
  "The Commission shall be the controller of the EU database." It has no explicit definition
  phrasing, so it is outside Fix 1's scope by construction.
* **`rg_048`** improved to a composed KB summary but still does not state the Art 3(26)/(27)
  definitions.
* **`_USER_INFORMATION_INTERACT_RE`** still fires on a non-natural-person subject
  ("Must an employer be informed when workers interact with AI systems"). Recorded precision
  note; tightening it needs its own corpus measurement.
* The `REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN` paired easy gate remains unrun: the
  Claude-Max wrapper's CLI is still quota-blocked (§5.4/§6). The Bedrock stand-in
  (`docs/measurements/r411/wrapper_stub_bedrock.py`) is built and smoke-tested for it.
* `easyhard_ab` scores the official *reference* axes only; the Ans Correctness deltas above
  come from the re-judge instrument, not from a gold gate.
