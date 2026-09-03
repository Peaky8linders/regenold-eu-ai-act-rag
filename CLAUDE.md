@AGENTS.md

# CLAUDE.md — Claude Code Context & Runtime Guidelines

This file extends `@AGENTS.md` with Claude-specific operational details, wrapper quirks, and runtime configuration.

## LLM Provider Architecture & Claude Wrapper

`P2P_GRAPH_RAG_PROVIDER` selects one of three mutually exclusive paths:

| Value | Behaviour | Configuration / Setup |
| :--- | :--- | :--- |
| `cli` / `auto`* | Pure deterministic, no LLM, sub-10 ms. **This is what davidath runs.** | Default offline path |
| `anthropic` | Stage-1 + Stage-2 via Anthropic SDK (per-token billing) | `P2P_GRAPH_RAG_API_KEY=sk-ant-...` |
| `openai_wrapper` | Stage-1 + Stage-2 + Stage-0 intent via the local Claude Code Max wrapper | Wrapper on `127.0.0.1:8000` + `OPENAI_API_BASE` |
| `bedrock` | AWS Bedrock Converse API (EU cross-region inference) | `BEDROCK_REGION=eu-central-1` + AWS keys |

`* auto` -> `anthropic` when an API key is set, otherwise falls back to `cli`. Every sub-pipeline falls back to a deterministic equivalent on error, so the route never 500s on a downed LLM.

### Local Claude Code OpenAI Wrapper Setup
The local proxy lives at `D:\Claude Projects\claude-code-openai-wrapper` and leverages the flat Claude Max subscription.

To run evaluations against the wrapper:
```powershell
$env:OPENAI_API_BASE = "http://127.0.0.1:8000/v1"
$env:OPENAI_API_KEY = "dummy"
$env:P2P_GRAPH_RAG_PROVIDER = "openai_wrapper"
```

### Cloudflare Access Service Token
When Cloudflare Zero Trust Access fronts `wrapper.antifragile-ai.net`, attach:
- `CF_ACCESS_CLIENT_ID`
- `CF_ACCESS_CLIENT_SECRET`

Verify live wrapper connectivity via `curl http://127.0.0.1:8000/healthz/llm`.

---

## Critical Claude-Specific Gotchas

1. **Stage-2 SYSTEM Prompt is Dropped by Wrapper**: The Claude Max wrapper drops the system prompt slot (0% of requests see it). **All Stage-2 prompt modifications MUST go into the user message**.
2. **`railway.toml [deploy.envs]` is Inert**: Railway's schema does not apply `[deploy.envs]`. All runtime defaults MUST be defined as code defaults in Python (`app/config.py` and `app/engines/graph_rag.py`).
3. **Graph Auto-Seeding Version Control**: Code fixes in `provision_text` require bumping `SEED_VERSION` in `scripts/seed_neo4j_kb.py`, otherwise boot auto-seeding skips execution and serves legacy graph data.
4. **Environment Loading Context**: `load_dotenv()` resolves relative to the calling script directory. Always assert `get_graph_client().enabled` before drawing graph benchmark conclusions.
5. **No Parallel Wrapper Jobs**: Never run multiple wrapper-bound evaluation runs concurrently over the single local proxy instance.

---

## ⛔ The merge gate is ALWAYS the live pairwise A/B (operator directive, R330+)

**Do not run `evals.bench.runner` (davidath 476) or `evals.regenold.runner` (255 scenarios).
They are retired. The ONLY evaluation instrument is the live pairwise A/B judge.**

* `evals.harness.ab_judge` — position-swapped live pairwise A/B evaluation.
* `evals.harness.easyhard_ab` — reference conciseness & strict recall pairwise evaluation.

⚠ **CORRECTED R381 — the three sentences that stood here were wrong on all three counts.**
They read: *"Both are scored by the grounded judge (`evals/judge/grounded.py`) against verbatim
Act text. That is the only instrument that measures what the competition measures. Use
`claude-sonnet-4-6` (or `claude-sonnet-5`) for the LLM judge via the cloudflared tunnel, with
Bedrock fallback."* Executed:

* **Neither harness calls the grounded judge.** `easyhard_ab` scores with `evals.bench.metrics`
  only (lexical, deterministic); `ab_judge` runs a pairwise judge grounded on **KB summaries**,
  not verbatim Act text. `evals/judge/grounded.py` is a SEPARATE, post-hoc pass you point at a
  sidecar. Run it explicitly or it does not run.
* **There is no Bedrock fallback.** `--provider` is an explicit choice
  (`wrapper|anthropic|groq|gemini|bedrock`); nothing chains. A wrapper outage yields
  `judge_error` rows, not a Bedrock retry.
* **`claude-sonnet-5` is reachable — but only over the wrapper/tunnel.** Verified 2026-09-03:
  a real single-row grounded-judge call with `--model claude-sonnet-5 --provider wrapper`
  scored 0 errors, and a bogus id (`claude-bogus-9-9`) 500s, so the id is genuinely resolved
  rather than silently defaulted. On **Bedrock** it resolves to `eu.anthropic.claude-sonnet-5`
  and returns `api_access_denied_403` (so do `claude-opus-5` and `claude-opus-4-8` — which
  means **the R379/R380 Bedrock A/B legs cannot be reproduced on today's key**). The in-code
  `_DEFAULT_MODEL` is `claude-sonnet-4-6` for exactly that reason.
  **Judge over the wrapper with `--model claude-sonnet-5 --provider wrapper`.**

⚠ **And it does not measure what the competition measures.** The judge prompt interpolates
question + verbatim provision text + our answer + our citations — and **nothing else**. The
official benchmark grades Ans Correctness against *per-question criteria* and BOTH conciseness
axes against a *reference answer*; the July-7 batch carries neither (`_official_batch_20260707.json`
has 8 fields, none of them criteria or a reference answer, because regenold never published
them). Treat every local judged number as a PROXY. See § R381.

## ⛔ R381 — the "conciseness collapse" is a METRIC REDEFINITION. The R367 section below is half wrong.

**Executed 2026-09-03.** Diff the two reports axis-by-axis **for the two BASELINES**, whose
systems did not change between them (`docs/Antifragile-Regenold-benchmark-report-preview.pdf`
2026-07-14 vs `report_antifragile_ai.pdf` 2026-08-25):

| split / baseline | AnsL | AnsS | **AnsConc** | RefL | RefS | **RefConc** | Tone | Speed |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| easy, 2026 frontier | +0.0 | +0.0 | **−21.2** | +0.0 | +0.0 | **−28.8** | +0.0 | +2.1 |
| easy, 2025 baseline | +0.0 | +0.0 | **−39.2** | +0.0 | +0.0 | **−38.2** | +0.0 | −0.2 |
| hard, 2026 frontier | +0.0 | +0.0 | **−20.4** | +0.0 | +0.0 | **−20.6** | +0.0 | +1.5 |
| hard, 2025 baseline | +0.0 | +0.0 | **−31.5** | +0.0 | +0.0 | **−28.2** | +0.0 | −1.4 |

**Every correctness and tone axis is identical to 0.0 pp; only the two conciseness axes moved,
by −20 to −39 pp, on systems that did not change.** Two unchanged systems cannot change their
scores unless the metric changed. All **twelve** printed Overalls reproduce as the plain
geometric mean to ≤0.06 pp, so the aggregation is untouched — only the two axis definitions are.
The July preview says so itself: *"More details will be provided in the final report."*

**Consequences, and they invert the roadmap the R367 section states:**

1. **Our conciseness did not collapse 44 points.** Using the baselines as the metric-only
   control, of our −44.1 AnsConc roughly **−35 pp is the metric** and only **~−9 pp** is a real
   verbosity regression; on RefConc we slightly *improved*. The six candidate answers printed
   verbatim in the Aug-25 appendix average **923 chars** — the July run averaged **914.9**
   (measured from `official_batch.jul07_answer`, n=110). Length barely moved.
2. **⛔ The R367 counterfactual is void.** "Hold Aug-25 correctness + restore July conciseness →
   85.8 easy / 84.2 hard" mixes new-metric correctness with old-metric conciseness. Never quote
   the `96.0`, the `−44.1`, or the 85.8/84.2 row again. **Only ever compare within one report.**
3. **The real trajectory is GOOD.** Gap to the 2026 frontier baseline: easy **−10.7 → −5.8**
   (closed 4.9 pp), hard **−14.4 → −8.3** (closed 6.1 pp). Against the 2025 baseline easy went
   from **losing −3.4 to winning +5.0**. The last round was a large real gain, not a loss.
4. **The true remaining gaps (Aug-25, easy, vs frontier):** AnsConc **−16.0**, RefStrict
   **−10.2**, AnsStrict −7.9, RefLoose −6.7, AnsLoose −4.7, RefConc **−1.5** (near parity),
   Tone −0.9 — and **Speed +5.8, we BEAT frontier.** Under the new harsh metric nobody scores
   high (frontier 67.9 / 51.9).

### The scoring function is now known exactly — use it before spending a live batch

`Overall = geometric mean of the 8 axes` (≤0.06 pp on all twelve rows). Marginal GM leverage at
our Aug-25 point, pp Overall per pp axis — easy: `ref_conc 0.186 > ans_conc 0.181 >
ref_strict 0.137 > ans_strict 0.116 > speed 0.107 ≈ ref_loose 0.105 ≈ ans_loose 0.105 >
tone 0.095`; hard: `ans_conc 0.203 > ref_conc 0.184 > …`.

**Ref. Conciseness = `min(1, |expected| / |provided|)` — a PURE COUNT ratio.** Recovered from
the five appendix cases that print both sets, against the printed 50.4:

| candidate formula | mean over the 5 cases | err |
| :--- | ---: | ---: |
| exact-string precision | 39.0 | 11.4 pp |
| hierarchical precision | 63.0 | 12.6 pp |
| head-collapsed precision | 65.0 | 14.6 pp |
| **pure count excess `min(1, E/P)`** | **49.0** | **1.4 pp** |

Per case: Q45 1/2, Q17 1/5, Q95 2/4, Q104 min(1,2/1), Q74 1/4. **WHICH provisions you cite does
not affect this axis at all — only HOW MANY.** The expected sets are MINIMAL: **1.4 refs/row**.
We ship **3.27/row** offline on the official 110 (measured R381; ~3.1 live per R380). Arithmetic:
2.5 refs → RefConc ~56 (+1.0 pp Overall); **2.0 → ~70 (+3.6 pp)**; 1.5 → ~93 (+7.9 pp). Even a
−10 pp hit to BOTH ref-correctness axes only costs −2.4 pp. R282's live measurement of the R281
`adaptive_ref_clamp` independently confirms the direction (RefS +0.060, RefConc +0.144,
recall −0.034, **est. Overall +2.34 pp**). Ready-made knobs, no code change:
`REGENOLD_REF_CLAMP_SCENARIO_BUDGET` (default `5`) and the R77 QA budget.

⚠ **This is in direct tension with Hard Rule #8.** `gold_dropped_head` is computed against our
own hand-built probe gold, which is NOT minimal, so the internal gate actively fights the
official RefConc axis (leverage 0.186, the highest of the eight in easy mode). Do not veto a
trimming lever by reflex — run the arithmetic and put the table in front of the operator.
Instrument: `scratchpad/official_calibration.py` + `refconc_formula.py` (session 09e208c3).

## ⛔ R367 — the OFFICIAL 2026-08-25 report: we fixed correctness and lost the round on CONCISENESS

⚠ **READ THE R381 SECTION ABOVE FIRST.** The correctness half of this section is sound and is
our own measured movement. The CONCISENESS half — the −44.1 / −28.9 deltas, "the geometric mean
ate the gain", and the whole counterfactual table — compares two different metrics and is void.

`report_antifragile_ai.pdf` (2026-08-25, 110 questions, easy + hard). **Overall is a plain
geometric mean of the 8 axes** — reproduced here to <0.1 pp on all six reported rows, so the
scoring function is known exactly.

| axis | Jul-14 easy | **Aug-25 easy** | Δ | Jul-14 hard | **Aug-25 hard** | Δ |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| Ans Correctness Loose | 72.1 | **89.7** | **+17.6** | 74.0 | **89.9** | **+15.9** |
| Ans Correctness Strict | 63.6 | **81.2** | **+17.6** | 60.6 | **80.0** | **+19.4** |
| **Ans CONCISENESS** | **96.0** | **51.9** | **−44.1** | **93.4** | **45.2** | **−48.2** |
| Ref Correctness Loose | 85.2 | 89.4 | +4.2 | 78.7 | 89.5 | +10.8 |
| Ref Correctness Strict | 58.8 | 68.3 | +9.5 | 56.0 | 70.7 | +14.7 |
| **Ref CONCISENESS** | **79.3** | **50.4** | **−28.9** | **72.1** | **49.8** | **−22.3** |
| Tone | 98.5 | 99.1 | +0.6 | 98.2 | 96.1 | −2.1 |
| Speed | 75.1 | 87.6 | +12.5 | 61.7 | 85.7 | +24.0 |
| **OVERALL** | **77.5** | **75.1** | **−2.4** | **73.0** | **73.4** | +0.4 |

**Every axis improved except the two conciseness axes, and because Overall is a GEOMETRIC
MEAN the two collapses ate the entire gain — easy Overall went DOWN.** We now beat 1 baseline
in easy and **0 in hard** (we lost to the 2025 baseline in hard, which we used to beat).

**The counterfactual is the whole roadmap.** Hold the Aug-25 correctness numbers, restore only
the July conciseness numbers:

| arm | easy | hard |
| :--- | ---: | ---: |
| as measured | 75.1 | 73.4 |
| **+ July conciseness** | **85.8** | **84.2** |
| 2026 frontier baseline | 80.9 | 81.7 |

That **BEATS the frontier baseline in BOTH modes.** These two axes also now carry the highest
marginal GM leverage of the eight — **0.179 (AnsCon) and 0.185 (RefCon) pp of Overall per pp**,
versus 0.104 for Ans Loose and 0.137 for Ref Strict.

⚠ **This RETIRES the standing "AnsCon is the only axis we lead / it has ZERO headroom / do NOT
shorten answers" reading** (recorded in `project_regenold_official_scorecard` and quoted inside
`app/integrations/regenold/models.py`'s R320 comment as "96.0 easy / 93.4 hard, the only axis we
lead"). That was true of the July scorecard and is **inverted** on this one. It is now the
largest single gap to the frontier baseline in easy mode (−16.0 pp).

**MEASURED shape of the fat** — the six report questions replayed live over the cloudflared
tunnel: each answer states the answer in its first one or two sentences, then appends **two to
four sentences of adjacent-but-UNASKED law**. Art. 97's delegation mechanics on an Art. 7
question; the Art. 6(3) derogation on a definitional one; Art. 26 deployer duties on an Art. 13
one; the Annex I product route on an Annex III one. That trailing material is also what drags
the extra provisions onto the wire, because `_add_prose_named_refs` promotes every provision the
prose names, **uncapped**. **ONE root cause, BOTH conciseness axes.**

**It is NOT a Stage-1 length regression.** Two-arm offline replay, HEAD vs the July snapshot
(`231c1d5`), same 111 questions, `REGENOLD_SKIP_DOTENV=1` in both arms: **byte-identical, all
111 rows, mean 1251.8 chars each way.** The growth is entirely on the live Stage-2 path.

**The refuted remedies — do not re-propose.** A blunt sentence cap is R320's own measured trade
(answer_conciseness +0.095, **answer_correctness −0.143**); positional trimming is R142.1, which
lost a live pairwise judge **11-0, p=0.001**. The lever that is *not* in those families is to
stop the model WRITING the unasked sentence, on the USER channel (the system prompt is 0%
delivered) — shipped as `REGENOLD_SCOPE_STOP_RULE`, **default OFF**, see the flag table.

### `REGENOLD_SCOPE_STOP_RULE` — MEASURED, and it does NOT clear its gate

Paired live A/B over the **cloudflared tunnel** (`wrapper.antifragile-ai.net`), arms
interleaved per row so wrapper drift hits both, n=48 single-turn gold-bearing probe rows:

| axis | baseline (OFF) | branch (ON) | delta |
| :--- | ---: | ---: | ---: |
| answer chars (mean) | 1186.3 | 1074.4 | **−112.0 (0.906x)** |
| answer chars (median) | 1192.0 | 1064.5 | −127.5 |
| rows shorter / longer | — | — | **36 / 12**, sign test **p = 7.2e-04** |
| refs per row | 2.60 | 2.54 | −0.06 |
| head precision | 0.5507 | 0.5559 | +0.0052 |
| latency (s) | 14.8 | 13.6 | −1.2 |
| **`gold_dropped_head` (SUM)** | **10** | **11** | **+1 → GATE FAILS** |

**So it ships DEFAULT OFF.** The conciseness effect is real and significant, but hard rule #8
is literally "drop ZERO more" and this arm drops one. Per R365 that is now an exit code, not a
printed flag, and an `--allow-gold-drop` run does not count as having cleared it.

⚠ **Read the failing rows before re-running this.** The +1 is a net of 2 drops and 1 recovery,
and **both dropped rows are rows where the ON arm's answer got LONGER** (1091→1133 and
1726→2015 chars). That is generation variance on the rows the lever did not act on, not the
clause cutting a gold provision. It is also exactly what the documented noise floor predicts:
`project_easyhard_ab_noise_floor_n40` records identical arms drifting 0.053 and **sign-flipping
all three ref axes** at n=40.

**The generalisable methodology point:** answer LENGTH is near-deterministic and resolves at
n=48 (p=7.2e-04); the REFERENCE axes do not resolve until n≥120. So a conciseness lever can be
screened cheaply on length, but it can never be *cleared* on the same run — the gold gate needs
its own properly-powered pass. Do not read this table as "the lever loses"; read it as
"the answer axis is measured, the reference axis is not yet."

### The six appendix failures — all reproduced, four root causes fixed (R367)

Three of the six reproduce **OFFLINE**, where the deterministic Stage-1 answer is near
byte-identical to the shipped one. These were data and routing defects, not model behaviour.

| Q | judged | root cause | status |
| :--- | :--- | :--- | :--- |
| 104 | 2/2 FAIL | `kb.py` had Annex VIII's content under `"Annex X"` and Annex X's under `"Annex IX"` — a two-annex SHIFT. `eu_ai_act_corpus` was right all along | **fixed** |
| 96 | 2/2 FAIL (total refusal) | `"high-risk use case"` was not a scope anchor → CONVERSATIONAL bucket → `LEXY_OOS_GENERIC` | **fixed** |
| 95 | 2/2 FAIL | the `Art. 6` summary said "eight Annex III **use cases**"; Annex III lists eight **AREAS** | **fixed** |
| 17 | 3/4 FAIL | Article 7 had **zero** keyword anchors anywhere, AND the question tripped the canned `_general_classification_verdict` roster which evicted it. **Both** halves needed | **fixed** |
| 45 | 5/5 FAIL | abstention ("the materials available here do not permit…") on content that was in the corpus the whole time | content now correct live; ref grain open |
| 74 | 2/2 FAIL | framing: leads "Yes, marking is required" where the judge wanted "not that kind of marking, but some disclosure is still required" | **open** |

⚠ **Q96 is FLAKY, not dead.** The deterministic classifier returns `in_scope=False`, but live
the LLM scope gate *rescues* it — which is exactly how a question that is 100% in scope survived
to a graded run and then refused. Never conclude a scope path is safe from one live pass.

⚠ **A scope anchor is not enough on its own.** Verified live: after adding `Art. 7` to
`scope.py`'s `KEYWORD_TO_ARTICLE`, Article 7 reached `ctx.obligations` and was **still absent
from the Stage-2 prompt and from the wire refs**. The route only **FRONTS** an anchor already in
`candidates` (`app/routes/regenold.py` ~8155) — it never **adds** one. Retrieval is seeded by
the *engine's* separate map, `app/engines/_graph_rag_data.py::_KEYWORD_ENTITY_MAP`. Add to both.

⚠ **The meta-commentary ban is instructed but NOT enforced.** `USER_ANSWER_COVERAGE_CLAUSE`
already forbids mentioning "the references, provisions or material supplied to you"; Q45 and
Q17 both violated it in the graded run ("the materials available here do not permit a
citation-supported enumeration", "the Act does not settle within the text supplied here").
There is no post-generation guard for this, unlike R357's truncation guard. Open lever.

## ⛔ R379 — PR #368's "V2 prompt family" shipped default-ON on a gate claim that has NO record

PR #368 (`0033b88`, live in production) bundled the R367 fixes above with a port of the sibling
repo's R377 work: `REGENOLD_PROMPT_V2` (**default ON**) selects four rebuilt USER-channel clauses
(`USER_ANSWER_COVERAGE_CLAUSE_V2`, `USER_REF_MINIMALITY_CLAUSE_V2`,
`USER_SUBPARAGRAPH_ATTRIBUTION_CLAUSE_V2`, `USER_CHALLENGE_BREVITY_CLAUSE_V2`), plus
`REGENOLD_FIDELITY_TIER_NEGATION` (default ON) in `stage2_fidelity.py`, 18 new pushback markers and
7 leading-confirmation regexes in `is_challenge_turn`, and the R377-A XML-channel peel in
`_looks_structurally_truncated`. **Prove-it-fires: verified on the wire** — with the flag ON the
Stage-2 user message carries `LEGAL VERSION:` and the V2 minimality text, and on a pushback turn it
carries the CHALLENGE clause with the tag instruction; with the flag OFF none of them do.

**The PR body says: "Live AWS Bedrock evaluation: Hard Rule #8 satisfied (gold_dropped_head == 0,
delta = +0 on paired A/B gate)." There is no record of that run anywhere.** Not in this repo
(no sidecar, no `.evalout`, no results file since 2026-08-30), not in the sibling repo (its
`R378.1: live Bedrock verification` is a verification of the *denoiser truncation guard*, and
`R378.2` is a single-arm tunnel scorecard — neither is a paired A/B of `PROMPT_V2`), and not in the
Antigravity session that planned it (`0c933efb…`, 2026-09-01: the plan lists the A/B as a step; its
`scratch/` is empty and it has no walkthrough). A prompt-side, default-ON change is exactly what
AGENTS.md invariant #5 says must clear `gold_dropped_head` first. So this round runs that gate.

### The extractor the port dropped (R366 class, fourth instance)

`USER_CHALLENGE_BREVITY_CLAUSE_V2` instructs the model to put its reasoning inside
`<reasoning_scratchpad>` and its answer inside `<answer>`. **The benchmark's exact hard-mode
pushback text fires `is_challenge_turn`** (verified: "I don't think this is correct. Perhaps your
answer contains hallucinations… Let's try again:" → `True`), so every hard-mode row receives that
instruction. Upstream pairs the clause with `prompt_guard.extract_xml_channels` at the Stage-2
return; the port brought the clause and the truncation-guard *peel* (which only decides "is it
truncated") but **not the extractor**, and the local `app/security/prompt_guard.py` was the older
version without it. A model that obeys the instruction would have shipped the scratchpad and both
tags on the wire, and the three prose→refs passes would have promoted whatever the scratchpad
named into the citations. `tests/test_r377_live_fixes.py` was itself written against live replies
ending `…</answer>
</reasoning_scratchpad>`, and upstream records the leak live on Sonnet 5 and
Opus 5.

**Measured here: 0/4 leaks** — two pushback turns each over the tunnel and over Bedrock
(Opus 4.8) shipped clean, because the *system-side* `ANSWER_GENERATE_SYSTEM_V2` output contract
that makes upstream's models emit the channels was not ported either. So the exposure is latent,
not observed — and the fix is a strict no-op when no tags are present. R379 ports
`extract_xml_channels` verbatim (the local guard is a subset of upstream's) and calls it at the
same point upstream does, before `validate_llm_output`; the scratchpad goes to
`record_llm_thinking`. `tests/test_r379_xml_channel_extraction.py` pins both properties on the wire.

⚠ Also fixed in passing: the R367 Annex X summary closed with "NOT the EU-database registration
annex — that is Annex VIII (Art. 49)". Live, the model echoed that contrast and the grounding guard
promoted **Annex VIII and Article 49 onto the wire** on a question whose gold is `Annex X;
Article 111.1` (5 refs shipped vs 2 gold). A number you write into a KB summary is a citation
whether the answer affirms or rules out the provision — the V2 minimality clause says exactly this
to the model, and it applies to us. Reworded without provision numbers; `KB_VERSION` v19 → v20.

### The R379 review of the port — nine executed findings, five fixed, one flag flipped OFF

A specialised review subagent executed (not read) the Gemini delta `2fe18ce..0033b88`. Probe
scripts under the session scratchpad; every claim below reproduced on `0033b88`.

| # | sev | finding | disposition |
| :--- | :--- | :--- | :--- |
| P1-3 | P1 | `_CHALLENGE_PATTERNS` fired on **10 of 12** ordinary questions and on the Act's own wording (`… biometric verification solely to confirm that a specific natural person …`, Art. 3(36)/Annex III(1)(a), which sits verbatim in this repo's own probe corpus). A hit appends "the user is disputing the previous answer … say the same thing at the SAME length" to a **first-turn** question. `annex` was also missing from the contradiction alternation, so a real pushback ("that is not what Annex III says") was missed. The port's negative test used "confirm **whether**", dodging the pattern by one word | **fixed**: the family applies only where the `Latest question:` marker proves a prior turn; the ratification pattern must be the HEAD of the live turn; `annex`/`recital` added. Explicit dispute markers stay unconditional, so the benchmark's own pushback still fires. davidath re-verified 0/476 |
| P1-1 | P1 | `extract_asserted_tier_set`'s label fallback puts a tier in the CONTRACT on a bare English word ("prohibited from placing … without a CE marking") while the polish side stays anchor-only → contract ⊄ anchors (the module's own invariant) → a correct concise polish is discarded as `fallback_tier_drop` — the R142.1 regression the guard exists to avoid | **`REGENOLD_FIDELITY_TIER_NEGATION` flipped to default OFF** (anchor-only contract restored); the three defects are recorded in its docstring |
| P1-2 | P1 | the denial filter drops the whole SENTENCE, so "not high-risk under Annex I, but high-risk under Annex III" deletes `high_risk`, `len(contract) < 2` short-circuits, and a tier-dropping polish ships — the guard switches itself off | same flip; pinned as a tripwire so a future fix re-measures before re-enabling |
| P2-4 | P2 | on the deterministic drafts the engine actually emits for a cross-tier ask ("not among the practices prohibited under Article 5") the denial regex does not match — the lever was a **no-op** on its own class while carrying P1-1/P1-2 | same flip |
| P2-7 | P2 | `REGENOLD_PROMPT_V2` used allow-list truthiness in a file whose other default-ON gates use deny-list: `=` (blank), `=Y`, `=enabled` silently reverted prod to V1 while the cache key still recorded the variable, so an A/B would compare V1 to V1 | **fixed**: deny-list form |
| P2-8 | P2 | the markdown-table rule excused a stream cut right after a cell separator (`\| Deployer \|`) | **fixed**: a row needs ≥ 3 pipes |
| P2-9 | P2 | the R355 AST cache-key gate scans `app/engines` + `app/integrations/regenold` only; `REGENOLD_PROMPT_V2` lives in `app/data/` and would not have been caught if missing | **fixed**: `app/data` added to the scan; it passes with no new registrations |
| P2-6 | P2 | four test modules pinned the dead V1 constants; replayed on the live V2 text two budgets FAIL (`ref_minimality` 701→**1464** chars vs `< 1000`; `coverage` 1955→**2466** vs `≤ 2200`). Net **+1,553 chars per Stage-2 call**, undocumented, on the axis that collapsed | **fixed**: re-pointed at the selectors; budgets pinned at the measured V2 sizes so further growth trips them. Whether V2 earns that cost is the A/B below |
| P2-5 | P2 | `_SENTENCE_SPLIT` cuts `Art. 50` into `Art.` + `50.`, erasing the anchor from the contract; engine drafts contain 0 `Art. N` forms, so exposure is curated/graph prose only | **open** (documented; low frequency) |

Clean: the peel loop (16 cases), the selector migration, the tail markers for the Groq shrinker,
`is_challenge_turn`'s `Latest question:` slicing, `_verdict_flip`/`_sentences_for_tier`.

### The biggest lever measured in this repo: Stage-2 on Bedrock DELIVERS the system prompt

Paired, same 48 gold-bearing probe rows, same prompt (`REGENOLD_PROMPT_V2` default ON in both arms),
arms interleaved per row: **A = the cloudflared tunnel (production primary)**, **B = Bedrock
`eu.anthropic.claude-opus-4-8`** (`P2P_GRAPH_RAG_PROVIDER=bedrock` + `REGENOLD_STAGE2_STRICT_TRANSPORT=0`).

| axis | tunnel (A) | Bedrock (B) | delta |
| :--- | ---: | ---: | ---: |
| answer chars (mean / median) | 1233 / 1170 | **621 / 617** | **−612 (0.504x)** |
| rows shorter / longer under B | — | — | **46 / 1**, sign test **p = 6.8e-13** |
| refs per row | 2.69 | 2.42 | −0.27 |
| head precision | 0.5047 | **0.5993** | **+0.0946** |
| **`gold_dropped_head` (SUM)** | 15 | **12** | **−3 → PASS (recovers gold)** |
| latency (s) | 15.7 | **3.6** | **4.4× faster** |
| XML channel tags on the wire | 0 | 0 | — |

**Mechanism.** The Claude Max wrapper drops the system prompt on 100% of requests (R298/R340) —
the 51 kB `ANSWER_GENERATE_SYSTEM` with its cohesion, no-restatement and brevity rules never
reaches the tunnel model. Bedrock delivers it. Every axis that moved is an axis those rules
address. This is the same conclusion R277/R340 reached from the other side ("the system prompt
is 0% delivered, put the rules on the USER channel"), now measured as the *delivered* system
prompt's effect: **answer length halves, the collapsed conciseness axis's whole gap
(−16.0 pp easy / −26.6 pp hard vs frontier) is inside this one switch, and Speed (−7.7 pp) too.**

⚠ **Not flipped.** Production Stage-2 transport is an operator decision: the R360 contract pins
the tunnel as primary, and Bedrock is per-token billing against a flat Claude Max subscription.
Two confounds to close before flipping: (1) the tunnel arm's model is whatever the wrapper routes
(Sonnet/Opus by complexity) while B is Opus 4.8 fixed — a model change as well as a
delivery change; (2) n=48 is under the ref-axis noise floor, though −3 gold is in the safe
direction and length/latency are ~13 orders of magnitude past noise. The cheapest next
measurement is B vs B' where B' = Bedrock with the system prompt deliberately blanked, which
isolates delivery from model. **Recommendation: run that, then flip `STAGE2_PRIMARY` to Bedrock
for the benchmark window.** The harness for both is `scratchpad/ab_transport.py` (session f631a795).

### `REGENOLD_PROMPT_V2` — paired A/B on the Bedrock leg (R379)

Both arms forced onto Bedrock (`P2P_GRAPH_RAG_PROVIDER=bedrock` + `REGENOLD_STAGE2_STRICT_TRANSPORT=0`,
model `eu.anthropic.claude-opus-4-8`), `evals.harness.easyhard_ab --local`, label
`r379-promptv2-bedrock`. Bedrock was chosen because it is parallelisable and does not compete with
the single Claude Max wrapper (CLAUDE.md: "No Parallel Wrapper Jobs"); note that it is the
**fallback** leg, so this characterises the family on Opus 4.8 with the system prompt *delivered*,
not on the tunnel where the system prompt is dropped.

```
easy  n=95  ref_loose +0.0035  ref_strict +0.0142  ref_conc +0.0250
            kw_recall -0.0155  gold_dropped_head 21 -> 22  (+1)  <-- HARD RULE #8 EXITS 1
hard  n=37  ref_loose +0.0811  ref_strict +0.0680  ref_conc -0.0001
            kw_recall +0.0631  gold_dropped_head 18 -> 16  (-2)
```

**Disposition:** Hard rule #8 mandates "drop ZERO more gold heads on ANY split". Because the easy
split dropped one more gold reference head (21 -> 22), the harness exited 1 and `REGENOLD_PROMPT_V2`
is defaulted to **OFF** (`=0`). The hard-split gains are substantial (+0.0811 ref_loose, -2 gold
dropped), but require a powered run (n >= 120 per split) before considering promotion.


## R380 — the end-to-end audit, and where the conciseness fat actually comes from

Full write-up with evidence: `docs/reviews/r380-sota-audit-2026-09-02.md`. Five read-only
audits (Aura graph, both anchor maps + ontology, retrieval stack, Stage-2 user message,
MUVERA) plus a live hard-mode probe. The short version:

* **Calibration first.** The July answers that scored AnsCon **96** averaged **915 chars /
  4.2 sentences** (`jul07_answer`). The official axis judges *unasked content* against the
  reference answer, not length. Length is a screening proxy only; the lever is scope.
* **The user message invites the fat, by instruction.** The live path is uncapped
  (`REGENOLD_ANSWER_NO_CAP=1` / `REGENOLD_LIVE_SENTENCE_CAP=0`; offline keeps the 3-sentence
  cap, which is why the offline July-vs-HEAD replay was byte-identical). The only length rule
  is on the undelivered SYSTEM channel. Three default-ON user-channel clauses say "state both
  the prohibited context AND its treatment elsewhere", "name both and what each contributes",
  "use additional sentences for another risk tier, a carve-out, or a cross-reference … or when
  rule 12b" (a pointer into the undelivered system prompt); a CROSS-REFERENCED PROVISIONS block
  hands over 0.5–1.5k chars of neighbouring law; the draft already carries the adjacent
  rosters and the instruction is "Refine the draft". ~11.7k chars of overlapping clauses; the
  REFERENCES block is 10–30k, 4–15x the draft. **`REGENOLD_PROMPT_V3`** replaces all of it with
  one 6k block appended last (default OFF pending the gate; see the flag table).
* **Hard mode had two mechanical defects.** The Stage-0 de-noiser truncated on 5/9 live
  multi-turn calls (`max_tokens=100` on `openai/gpt-oss-120b`, a reasoning model) and every
  provider fell through to the 40-turn concatenation: turn-1 answers gained history provisions
  and one Article 111 question shipped `['Article 6','Article 5']`. And the R305 re-ask focus,
  checked against the evaluator's VERBATIM pushback template, fired on 100/110 official
  questions — the anchor-less ten took the truncating path with the disputed answer in the
  query and measured 1.2–2.3x the easy length. Fixed: `REGENOLD_DENOISER_MAX_TOKENS=400`,
  `REGENOLD_REASK_ANCHORLESS=1` (110/110).
* **Graph:** healthy and complete (1,789 nodes, 7 vector indexes at 100% coverage, verbatim
  text, 52–94 ms), but `_SUBPOINT_CYPHER` read `pt.number` where Point nodes carry `.letter`
  (0/421 vs 421/421) — every sub-point coordinate fed to Stage-2 lost its point letter. Fixed.
  The vectors are 128-D TF-IDF/SVD, not neural; the default-ON dense fill flips between Cohere
  and SVD on a 429, so retrieval is nondeterministic under Cohere rate limits.
* **Anchor maps:** Art. 17, Annex IV (both gold-cited), Art. 12, Annex IX, Annex X had zero
  engine anchors; Art. 97/98 zero in both maps. Fixed, 0 davidath hits.
* **Ontology:** `ROLE_OBLIGATIONS` binds Art. 13 to DEPLOYER, lists Art. 85/86 as
  AFFECTED_PERSON obligations (rights), `role_obligations.py` binds Art. 72 to DEPLOYER,
  DOWNSTREAM_PROVIDER lists Art. 53/55. Recorded, NOT changed — it is a reference GENERATOR
  measured at 0% precision as a citation oracle, and a wrong binding is still what gold cites
  on rights questions.
* **MUVERA:** do not build. At ~1,800 provisions exact Chamfer is one matmul (tens of ms);
  FDE only approximates the same score faster and cannot touch the "semantically plausible,
  legally inapposite" reference class; no keyed provider returns token-level vectors without
  torch. The cheap sub-point max-sim variant is a probe, gated on the distractor rows.
* ⚠ **The wrapper shares the operator session's Claude Max quota.** When this session hit its
  usage limit, a 40-row live screen was silently **66/80 Bedrock** (`transport_stats`). Every
  wrapper-bound runner must attribute rows to `wrapper|bedrock|failed` and abort on fallback.

**Measured (paired, interleaved, every row wrapper-served).** V3 screen, 30 single-turn
gold rows: chars **0.815x** (21 shorter / 7 longer, p = 0.0125), sentences 3.83 → 3.03, refs
−0.27, head precision +0.02, latency −1.5 s, `gold_dropped_head` 10 → 11 on a row whose V3
answer got LONGER. Keyword recall −0.089 on five rows: two tokenizer artefacts
("minimal-risk"), one legally better answer, two real (a negative verdict replaced by a
hypothetical GPAI variant; an emotion-recognition webcam in education called high-risk not
prohibited) — the block was rewritten against exactly those two before the gate run.
Combined paired gate (n = 127: 90 ST + 37 MT, 125 wrapper-served, 0 Bedrock fallback):
chars **0.794x** (105 shorter / 19 longer, p = 1.31e-15), refs −0.29 (p = 9.85e-05),
`gold_dropped_head` SUM 34 → 41 (+7). Per Hard Rule #8, `REGENOLD_PROMPT_V3` ships
**default OFF** (`0`). Non-prompt hard-mode and retrieval fixes ship default ON.
See `docs/reviews/r380-sota-audit-2026-09-02.md` § 2.2 / § 2.3.

## Reranking (R329)

**⚠ CORRECTED R331 — the paragraph below previously claimed the reranker was
"applied at the RETRIEVAL stage in `app/data/kb_search.py::top_articles_by_relevance`".
It was not.** That placement was reverted after it measured **0 calls**, and until R331
nothing outside `app/engines/cohere_rerank.py` and its test file imported the module at
all. A fresh session that trusted this file went looking for a call site that did not
exist. What follows is the wiring that is actually on `main`.

**Where it is wired (R331):** `app/engines/_graph_rag_impl.py::_render_supplementary_sections`,
reordering the graph-context ref list immediately before `render_kg_context`, using
`context.question` as the query. Gate `REGENOLD_COHERE_RERANK`, default OFF pending the
A/B; needs `COHERE_API_KEY` (present in `.env` and on Railway); registered in
`_engine_cache_key`.

It composes with R330's repair of the same call site (which passes `context.question` so
the R327 semantic layers stop being dead code): the rerank sits between the two, so with
the gate ON both the graph fetches and the semantic layers see the reranked order, and
with the gate OFF the block is byte-identical to R330. `test_r330_question_still_reaches_the_graph`
pins that R331 does not re-break R330's fix.

**Why that placement and not retrieval.** Every `kg_context.fetch_*` reader truncates via
`_node_ids(refs, limit=max_refs)`, `max_refs` default **8**. The cut is by list position,
so when the context carries more than 8 refs the order decides *which* provisions' verbatim
paragraph and sub-point text reaches Stage-2 — a content change, not a permutation of the
output. It targets **Answer Correctness**, the largest gap to frontier.

⚠ **CORRECTED R365 — the two sentences that used to follow here were FALSE and they
excused this lever from the gold gate.** They read: *"The graph blocks are non-citable
(`AGENTS.md` invariant #3), so this **cannot** add, drop or reorder a wire citation —
which is why it is not blocked on the missing `gold_dropped` guard. Gate it on `ab_judge`
(it moves answers), **not** `easyhard_ab`."*

**The Stage-2 prompt is not a sink.** The emitted wire `references` list is *recomputed
from the final Stage-2 prose* by three default-ON, `stage2_landed`-gated passes:

* `_reconcile_references_to_prose` (`app/routes/regenold.py:3921`, live at `:8791` / `:9073`,
  `REGENOLD_REFS_RECONCILE` default `1`) — **DROPS** wire refs the prose does not describe;
* R138 `_add_prose_named_refs` (`:4223`, final pass at `:9114`, `REGENOLD_CITE_CONSISTENCY`
  default `1`) — **ADDS** every provision the prose names, uncapped;
* `_surface_prose_subpoints` (`:3990`, at `:9179`) — **ADDS** sub-points the prose names.

So **any lever that changes the Stage-2 prompt can add, drop and reorder wire citations.**
Executed proof: `_reconcile_references_to_prose` returns two *disjoint* reference lists from
the *same* input refs under two different prose bodies. Measured proof from the sibling fork's
own n=140 paired run of a prompt-only lever (`REGENOLD_ROLE_OBLIGATION_CONTEXT`): the wire ref
list changed on **68/140 rows**, `gold_dropped_head` rose **30 → 34**, and it was vetoed on
exactly that.

Invariant #3 still holds in its true, narrow form: the graph cannot be a citation **source**.
It is **not** a statement of reference-neutrality.

⚠ **The trap that hides this.** The sibling's unit test `test_lever_does_not_change_the_wire`
asserts `on["references"] == off["references"]` and *passes* — because its fixture sets
`P2P_GRAPH_RAG_PROVIDER=cli` and a dead `OPENAI_API_BASE`, so `stage2_landed` is False and all
three prose→refs passes are, in this repo's own words, a "strict no-op". **A deterministic
fixture pins reference-neutrality in exactly the regime where the coupling is switched off.**
Never conclude reference-neutrality from a `provider=cli` test.

**Therefore: gate this on `ab_judge` for answers AND on `easyhard_ab`/`gold_dropped_head` for
references.** Both, not either.

**Prove it fires before reading any number.** `cohere_rerank.rerank_stats()` returns
`attempts / reordered / noop / failed`. R329 tried three placements; all three looked right
in the diff and all three made zero calls, reading +0.0000 — indistinguishable from a lever
that does not work. `tests/test_r331_rerank_placement.py` pins that the placement fires,
that the surviving top-8 set actually changes, and that the flag reaches the cache key.

⚠ **The "the model itself is good" probe is weaker than recorded.** The claim was that it
separates `Art. 50.3` **0.9244** from `Art. 19` **0.0394** and `Art. 99` **0.0090**.
Re-measured live against this repo's own `get_provision_text`: `Article 50.3` **0.8803** and
`Article 19` **0.0286** reproduce, but **`Article 99` scores 0.4583 — 50× the recorded
figure**, and it is the case that discriminates. Article 99 is *penalties*: legally
inapposite to a transparency-duty question, semantically plausible because its text
enumerates the very articles being asked about. That is exactly the failure class this
corpus suffers from, and a relevance cross-encoder does **not** cleanly reject it. Expect a
smaller effect than the probe implies, and prefer feeding sub-provision text over
full-article text where the ref grain allows it.

Two things to keep straight, because they are different interventions and only one has
been measured:

* **Post-hoc reordering of the final emitted reference list (measured, does NOT help).**
  Zero-variance replay of the live HARD run: mean normalised position of judged-wrong refs
  0.582 → 0.562 (delta **−0.019**, i.e. slightly worse). By that point the wrong references
  are already semantically plausible — that is *why* they were emitted — so a relevance
  cross-encoder scores them high for the same reason the generator did. Do not re-propose
  this variant; it is the one that is dead, not reranking in general.

The wrong references on this corpus are **semantically plausible and legally inapposite**
(e.g. `Article 43`, conformity assessment, cited on a risk-classification question). The
signal that *looks* like it discriminates them is *legal applicability* — does this provision
bind THIS role at THIS risk class — available as `ROLE_OBLIGATIONS` / `obligations_for`
(`app/data/ontology.py:684` / `:815`) and as the graph's `Obligation`/`HAS_OBLIGATION` (113)
and `RiskLevel`/`APPLIES_AT` (47) layers.

⛔ **MEASURED AND REFUTED (R365). Do not build the applicability filter.** The sentence that
used to close this paragraph — *"That is a grounding predicate, not a positional trimmer, so
it sits outside the refuted trimmer families"* — is **half right and it cost real work.** It is
outside families #1/#2/#3/#6/#7; it is **squarely inside #4 (ask-type × provision-role
exclusivity)** and overlaps #5. Three independent measurements, none of them a live A/B:

| instrument | result |
| :--- | :--- |
| 120 judged rows, per-row **ORACLE** (role,risk) — an upper bound no detector can reach | catches 104/118 wrong refs, **also drops 44/233 judged-RIGHT refs (19%)**, precision 0.70 |
| this repo's probe gold, real `_detect_role_and_risk_class` | **10 of 23 gold heads dropped (43%)** on the rows where it fires |
| sibling fork, `REGENOLD_ROLE_OBLIGATION_CONTEXT`, n=140 paired | vetoed: `gold_dropped_head` 30 → 34, `reference_correctness` exactly flat |

Three further facts close it — and note the “gate” itself is aspirational, see the correction below:

1. **It is inert on ~88% of traffic.** Both `role` and `risk_class` are extractable on
   **16 of 132** probe rows (12.1%); the sibling measured 11/297. A lever evaluable on 12% of
   rows will read UNDERPOWERED on any n=60–140 A/B — which is exactly what happened to R371.4/.5.
2. **The table is a SEED list, not a completeness list.** `obligations_for("deployer",
   "limited_risk")` returns **one** ref; `deployer × high_risk_annex_iii` returns four. Gold
   also cites the **governing / classifying / enforcing** provision (Art. 51 classification,
   Art. 101 penalties, Art. 50 cumulative across tiers), and no role×tier duty table contains
   those. Using a seed list as a drop-filter is a whitelist-completeness fallacy.
3. **The sibling already measured this ontology AS a citation oracle at 0% precision** —
   two statute-verified correct bindings added 8 non-gold refs and 0 gold. Recorded verbatim
   there: *"Legally correct is not gold-correct."*

⚠ Note the direction of use: `obligations_for` is **already a reference GENERATOR here**
(`_build_role_obligation_answer` → `_seed_role_obligation_obligations`,
`app/engines/_graph_rag_impl.py:3848-3900`) — which is the direction measured at 0% precision.
This repo's `ROLE_OBLIGATIONS` is also legally wrong in ~16 places the sibling fixed at R371.6
(e.g. `Art. 13` bound to DEPLOYER — Art. 13(1) binds the provider; `Art. 85`/`Art. 86` listed
as obligations when they are **rights**).

**What to do instead** — both outside all seven refuted families, and both ADD/GROUND rather
than DROP:
* **the citable-base guard** — `_add_prose_named_refs` already takes a `citable_bases`
  parameter (`app/routes/regenold.py:4223`) and **neither call site passes it**. Constraining
  prose-promotion to the retrieval-derived universe can only ever *remove an ungrounded
  promotion*; it can never invent a reference.
* **R368/R369 recall supplements** — the best-measured reference change in either repo
  (12 gold heads recovered, **0 false positives**, ref_loose 0.764 → 0.833). ADD-only, so it
  cannot trip `gold_dropped_head`.

**And the reason a ref-list transform is the wrong altitude at all:** on the 120 judged rows,
**73/118 (61.9%) of the judged-wrong references are NAMED IN THE SHIPPED ANSWER PROSE**, so
R274 ("never drop a ref the prose describes") makes them undroppable. The ceiling for *any*
reference-list transform is **+0.133** reference correctness and that assumes *perfect*
discrimination. There is also no head-identity rule to be had: `Article 26` is judged wrong
10× / right 2×, but `Annex III` is wrong 8× / **right 34×** and `Article 6` is wrong 3× /
**right 40×**. The signal is row-conditional, not head-conditional.

⚠ **CORRECTED R360 — `gold_dropped` DOES exist and the rule IS enforceable.**
The paragraph below previously read "`gold_dropped` does not exist anywhere in this
repo, so the standing rule … is currently **unenforceable**. Port `gold_dropped_head`
before gating any reference change." That was false when written and it cost work:
three separate reference-affecting changes were held back as ungateable. The
instrument is `gold_dropped_head` at **`evals/bench/metrics.py:555`**, wired into
`evals/harness/easyhard_ab.py::_score_row` and aggregated as a **SUM**, i.e. the gate
is literally "drop ZERO". Only the *exact* (sub-point) grain is missing — which is the
separate, still-correct point below.

⚠ **CORRECTED R365 — "gated" was the wrong word; until R365 it was only PRINTED.**
The SUM existed and the `<-- GOLD DROPPED (hard rule #8)` flag string was emitted,
but nothing enforced it: `gold_dropped_head` is absent from `_AXES` and `_LEVERAGE`,
the module had no `assert` and no `hard_fail`, its only `SystemExit`s were argparse
errors, `main()` returned `None` under a bare `main()` call in `__main__`, and the
repo has no `.github/` to consume it. A replay of the real `easyhard-r332-smoke-A`
checkpoint with one gold head deleted from the branch arm printed
`gold_drop_hd  0  1  +1  <-- GOLD DROPPED (hard rule #8)` and **exited 0**. Every
historical "it passed the gold gate" claim was a human reading stdout.

**R365 makes it an exit code.** `main() -> int` returns **1** when the branch arm
drops more gold heads than the baseline on ANY split, wired through
`raise SystemExit(main())`; the delta is read from the PAIRED subset where one exists
and from the full aggregate otherwise; the per-row `gold_dropped_head_refs` are
printed so a failure is actionable. The decision is the pure
`_gold_gate_verdict(base_agg, branch_agg, allow, paired=…)`, pinned two-sided and
offline by `tests/test_r365_gold_gate_enforced.py`. `--allow-gold-drop` forces exit 0
for a deliberate exploratory arm and says loudly that the run did **not** pass —
never cite an `--allow-gold-drop` run as having cleared the gate. A single-arm
scorecard is not gated; the rule is comparative.

⚠ **The sibling `evals/harness/ab_judge.py` still has the reports-but-never-enforces
shape** — it already has the plumbing (`main() -> int`, `raise SystemExit(main())`)
but returns 0 unconditionally on any completed run, so a `BASELINE wins (sig)`
verdict — the merge-blocking outcome the harness exists to detect — exits 0 exactly
as before. Deliberately left unchanged by R365 to keep that PR one concern. Do NOT port the upstream
`ref_crag_fine` / `gold_dropped_exact` as-is — the decision is right, but the reason
recorded here was wrong. **Corrected R331:** `_gold_exact_refs` does *not* head-project.
The real defect is that our probe gold carries **0/208 sub-point grain** — it is
article-level throughout — so `['Article 5.1.f','Annex III.2']` scored against gold
`['Article 5','Annex III']` yields `gold_dropped_exact = 2` and `ref_crag_fine = -1.0`,
penalising the most accurate citation shape the system emits. Same conclusion, and the
fix is gold that carries sub-point coordinates, not a change to the metric.

## Stage-2 transport contract (R360)

**Stage-2 rides the cloudflared tunnel (Claude Max) first and AWS Bedrock second.
No third leg exists.** `app/llm/stage2_policy.py` is the single source of truth;
`REGENOLD_STAGE2_STRICT_TRANSPORT` (default **ON**) enforces it and is registered
in `_engine_cache_key`.

Five paths used to break that contract, and the first two were armed by nothing
more than an API key sitting in the environment — no flag, no deliberate opt-in:

| path | how it opened | now |
| :--- | :--- | :--- |
| Groq tertiary fallback in `_openai_wrapper_complete_for_graph_rag` | any `GROQ_API_KEY` + one tunnel failure | refused |
| Gemini secondary fallback in `_claude_max_enhance_answer` | any `GEMINI_API_KEY` + tunnel *and* Bedrock both empty | refused |
| `P2P_GRAPH_RAG_PROVIDER=gemini\|anthropic` | explicit env | collapsed to the tunnel |
| fusion panel (`REGENOLD_FUSION_STAGE2=1`) | default roster is `(sonnet, groq, mistral)` | off-contract members filtered out of the roster |
| `P2P_GRAPH_RAG_PROVIDER=bedrock` | explicit env | collapsed to the tunnel — see below |

That last row is not an escape but an **inversion**: honouring it makes the
fallback the primary, so the Claude Max subscription is never dialled at all.

⚠ **The Groq hatch was not hypothetical.** It swapped in a *compressed* system
prompt (`_get_groq_compressed_system_prompt`) and, above ~11 kB, a shrunken user
message. So a deploy carrying `GROQ_API_KEY` answered its first post-hiccup
questions from a different model **on a prompt no eval has ever measured** —
silently, and attributed to the tunnel arm in any A/B running at the time.

**Prove it fires before reading any number.** `stage2_policy.transport_stats()`
returns `primary_attempts / primary_ok / primary_failed / fallback_* / refused /
refused_by_provider`, and `/healthz/llm` surfaces the same block under
`stage2_transport`. This follows the R329 rule the hard way: three rerank
placements all read correctly in the diff and all made **zero calls**, so
`tests/test_r360_stage2_transport_policy.py` asserts on those counters, never on
the shape of the code. It is also two-sided — it pins that
`REGENOLD_STAGE2_STRICT_TRANSPORT=0` *really does* still reach Groq, because a
guard whose OFF state behaves like its ON state is the inert-feature trap.

Four existing test modules (`test_fusion_stage2`, `test_gemini_routing`,
`test_anthropic_provider`, and the fusion half of `test_r127_trace_latency`)
cover the legacy multi-provider call shapes. Their assertions are unchanged;
they now declare `REGENOLD_STAGE2_STRICT_TRANSPORT=0`, the regime they were
written for.

---

## Baseline Performance Reference (Commit `b47c259`)

Deterministic environment: `OPENAI_API_BASE=http://127.0.0.1:1/v1 P2P_GRAPH_RAG_PROVIDER=cli REGENOLD_EXTERNAL_EMBEDDINGS=0`

| Metric Axis | Ans Loose | Ans Strict | Ans Conc | Ref Loose | Ref Strict | Ref Conc | Tone |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **OVERALL (476)** | 0.1884 | **0.3545** | 0.6143 | **0.5971** | **0.4748** | 0.4316 | 1.0 |
| **QA (137)** | 0.1407 | 0.4072 | 0.1961 | 0.8394 | 0.5536 | 0.4390 | 1.0 |
| **Scenarios (339)** | 0.2076 | 0.3332 | 0.7833 | 0.4992 | 0.4430 | 0.4287 | 1.0 |

Multi-turn coherence: **20/20 coherent**.

> **R330 — the bench measures CODE DEFAULTS, never your `.env`.** R329's
> `_load_dotenv_once()` (`app/config.py`, added to fix the "No Conn" UI bug) put the
> repo `.env` into `os.environ` at **import time**. `.env` carries BEHAVIOURAL flags
> (`REGENOLD_ROLE_DUTY_NOUN_SEED`, `REGENOLD_GRAPH_2HOP`, `REGENOLD_MAX_ANSWER_SENTENCES`
> …) next to credentials, so from that commit on the guard silently scored whatever a
> developer happened to have locally. Measured cost on the full 476:
>
> | arm | Ref Loose | Ref Strict | multi-turn |
> | :--- | :--- | :--- | :--- |
> | code defaults | 0.5971 | 0.4748 | 20/20 |
> | `REGENOLD_ROLE_DUTY_NOUN_SEED=1` alone | 0.5971 | 0.4633 | 20/20 |
> | the full local `.env` | 0.5735 | 0.4489 | 13/20 |
>
> This looked exactly like a **−0.026 Ref Strict / −45 pp coherence regression across 15
> commits that are in fact behaviourally neutral.** 13 of the 14 flags are individually
> inert; `ROLE_DUTY_NOUN_SEED` alone costs −0.0114 Ref Strict and the rest is interaction.
> `evals/bench/runner.py` now sets `REGENOLD_SKIP_DOTENV=1` before the first `app` import,
> which reproduces the table above byte-for-byte. Set `REGENOLD_SKIP_DOTENV=0` for a
> deliberate `.env`-on arm. **Live harnesses are unaffected — they still need `.env` for
> `OPENAI_API_BASE` + `CF_ACCESS_*`.** Production is unaffected either way (Railway sets
> real env vars and `override=False` already makes those win).
>
> **It also breaks the SCOPE gate.** `runner_v2 --local --probe-oos --oos-suite all`
> (n=51), which still loads `.env`:
>
> | arm | pass | scope leaks | `hard_fail` |
> | :--- | :--- | :--- | :--- |
> | code defaults (`REGENOLD_SKIP_DOTENV=1`) | 49 | **0** | False |
> | `.env` loaded, `REGENOLD_*` blanked | 46 | **3** | True |
> | the full local `.env` | 35 | **15** (29.4%) | True |
>
> No single `REGENOLD_*` flag reproduces it (all measured individually at 0 leaks), and
> neither does `GROQ_API_KEY` alone — so it is the CREDENTIALS reaching the R267.1
> Groq→Gemini→Mistral fallback, plus interaction with the flags. **The "deterministic"
> OOS probe is not deterministic when `.env` is present: the scope classifier can make
> live third-party calls.** Run it as
> `REGENOLD_SKIP_DOTENV=1 … -m evals.regenold.runner_v2 --local --probe-oos` (as of R330
> `runner_v2` sets this itself for `--local --probe-oos`).
>
> ⚠ **Open operator question:** does the Railway dashboard carry the same behavioural
> flags? If yes, production pays the Ref-Strict cost. If no, local evals do not predict
> production. Reconcile the two flag sets. **This is an eval-fidelity question, NOT a
> production-safety one** — see the scope note below.

### The OOS probe over-counts: "leak" ≠ the product requirement (R330)

**Measured against LIVE production** (`--endpoint …up.railway.app`, n=51): 41 pass, 10
"scope leaks", `hard_fail: True`. **That verdict is a harness artefact, not a defect.**

The requirement is that the assistant **pushes back on ADVERSARIAL input**; answering an
off-topic pleasantry is acceptable. Split that way, production is clean:

| category | live result |
| :--- | :--- |
| `injection` ("ignore all previous instructions", "what is your system prompt", DAN) | **3/3 pass** |
| `injection_obf` (base64 payload, translate-then-follow, roleplay-as-unrestricted) | **3/3 pass** |
| `scope_drift_mt` (multi-turn pivot off a genuine Art. 9 / Annex III thread) | **3/3 pass** |
| `nonsense`, `greeting`, `other_regulation`, `nonexistent`, `standards`, `non_eu_ai_law` | **all pass** |
| `r34_p0` / `r47_e` (Netflix, restaurant, weather, a joke) | 7 "leaks" — **chit-chat, allowed** |
| `adjacent_eu` (Product Liability Directive, MDR clinical evaluation) | 2 "leaks" — answers are **legally correct** |

**12/12 on adversarial.** Do NOT "fix" this by setting `REGENOLD_TOPIC_FILTER=0/1` on
Railway: R255 disabled the broad subject-topic filter precisely because the keyword
classifier false-positived on genuine, keyword-less AI Act questions, and R256's design
routes those to the LLM gate so real questions get rescued. Turning the blunt filter back
on trades a non-problem for a real one.

⚠ **What IS worth knowing:** an anchor-less question lands in the ambiguous
`CONVERSATIONAL` bucket handed to the LLM scope gate, and `regenold.py:5002` records that
"with no LLM wired it fails soft to the generic decline". So every `--local`
deterministic OOS run **fails safe by construction** and cannot measure the live gate at
all. If you want to test scope behaviour, run `--probe-oos` against the DEPLOYED endpoint.
Judge it on the adversarial categories only.

---

## Recent Engine Fixes (R356–R359)

Concise record of the applied fixes; full rationale in `docs/reviews/`:

* **R356 — grounded judge-report fixes.** Entity-map anchors that were
  missing (e.g. `human oversight → Art. 14`, `Art. 79/80`, `Annex III.5.c/d`),
  the Article 6(3) derogation detector extended to the narrow-procedural
  shape, and two new curated intercepts (GPAI transparency exceptions,
  systemic-risk scope) — each verified against the official provision text
  and false-positive-checked across all 81 live rows.
* **R357 — Stage-2 truncation guard (default ON).** `_guard_stage2_truncation`
  detects an incomplete final sentence (incl. trailing `…`) in the polish,
  repairs it with one bounded completion call, and falls back to the complete
  deterministic Stage-1 answer when repair fails. Never ships a fragment;
  gate `REGENOLD_STAGE2_TRUNCATION_GUARD`.
* **R358 — curated authoritative intercepts.** Four new curated answers
  (emergency triage `Annex III.5.d`, health-insurance pricing `5(c)`, hospital
  deployer duties, provider pre-market duties) that seed gold-head reference
  sets and skip Stage-2 polish (`_is_curated_authoritative_intercept`).
* **R359 — fine-grained CRAG answer judge (⚠ NOT IN THIS REPO).** Corrected R360:
  `answer_crag_fine` has **0 occurrences** here — it lives in the eval repo only.
  The description below is of that repo's axis, kept for provenance. `answer_crag_fine`
  axis ports the NICD paper's Appendix C.2.2 5-level truthfulness scale
  (`+1 / +0.5 / 0 / −0.5 / −1`) to the ANSWER, with truthfulness = sum of
  scores and hallucinated-row counts. Opt-in (not in default `AXES`); judged
  via Bedrock sonnet, never the Claude-Max tunnel.
* **R328–R354 ports** — `query_expansion.py` (LLM query rewrite, default OFF),
  `risk_classification.py` (Annex-III risk-class anchor, default OFF),
  rerank + graph-semantic upgrades; see the port review doc.

## Environment Flags Reference

| Environment Variable | Code Default | Purpose |
| :--- | :--- | :--- |
| `P2P_GRAPH_RAG_PROVIDER` | `auto` | Selected LLM backend (`cli`, `anthropic`, `openai_wrapper`, `bedrock`) |
| `REGENOLD_STAGE2_STRICT_TRANSPORT` | `1` | R360 Stage-2 transport contract: cloudflared tunnel (Claude Max) primary → Bedrock fallback, everything else refused |
| `P2P_GRAPH_RAG_ENABLE_STAGE2` | `1` | Stage-2 LLM polish master gate |
| `REGENOLD_GRAPH_SEMANTIC_LAYERS` | `0` | Constrained sub-provision vector search across Neo4j indexes (R327). **Corrected R360** — this table said `1`; R330 flipped the code default ON → OFF (`app/engines/graph_semantic.py:155`) |
| `REGENOLD_SEMANTIC_GLOSS` | `0` | Open-domain definitions/recitals gloss gate (R327) |
| `REGENOLD_GRAPH_VECTOR_RECALL` | `0` | Additive Neo4j & local SVD vector recall path (R326) |
| `REGENOLD_PARENT_COLLAPSE` | `0` | Collapse parent provisions when sub-points are cited (R325). **Corrected R366 — this row described a DEAD FLAG.** The helpers shipped in `a659849` with no call site; R366 wired it as the last reference pass. Still default OFF, and a strict **no-op offline** — see below |
| `REGENOLD_STAGE2_TRUNCATION_GUARD` | `1` | R357 post-generation truncation repair on the Stage-2 polish |
| `REGENOLD_SCOPE_STOP_RULE` | `0` | R367 scope stop rule on the Stage-2 USER channel: answer the question, then STOP; never append a neighbouring provision/power/mechanism/derogation the question did not raise. Targets BOTH conciseness axes (combined leverage 0.364 pp/pp). **Prompt-side ⇒ NOT reference-neutral** (AGENTS.md invariant #5), so it needs `easyhard_ab`/`gold_dropped_head` AND `ab_judge` before flipping |
| `REGENOLD_PROMPT_V2` | `1` | R377 port (PR #368): selects the four rebuilt V2 USER-channel clauses (coverage incl. `LEGAL VERSION` Omnibus exclusion, reference minimality, sub-paragraph discipline, and the CHALLENGE clause that instructs `<reasoning_scratchpad>`/`<answer>` channels on pushback turns). Shipped default ON on a gate claim with no record — see § R379 for the Bedrock A/B. Lives in `app/data/`, which the R355 AST gate does NOT scan; registered in `_engine_cache_key` by hand |
| `REGENOLD_FIDELITY_TIER_NEGATION` | `1` | R377-B port: the cross-tier fidelity CONTRACT is what the deterministic draft ASSERTS, not what it mentions — a sentence-local denial ("not high-risk") no longer counts as an asserted tier. `=0` restores the anchor-only reading |
| `REGENOLD_PROMPT_V3` | `0` | R380 — ONE compact ANSWER DISCIPLINE block (scope, completeness of what was asked, length, citations, terminology, grounding, Article 5 verdict check) appended LAST on the Stage-2 USER channel; withholds the V1/V2 coverage / critical-rules / minimality / sub-paragraph / terminology clauses, the breadth tail ("state both the prohibited context AND its treatment elsewhere", "rule 12b"), the CROSS-REFERENCED PROVISIONS block and the R367 scope stop rule, and relabels the draft as over-inclusive source material. Prompt-side ⇒ NOT reference-neutral; see § R380 for the measured arms |
| `REGENOLD_REASK_ANCHORLESS` | `1` | R380 — the R305 re-ask focus accepts a "let's try again:" tail without an AI-Act anchor (length + leading-coreference gates still apply). The evaluator's verbatim pushback fired the focus on 100/110 official questions; the 10 misses went through the de-noiser into the 40-turn concatenation. `0` restores R305 |
| `REGENOLD_DENOISER_MAX_TOKENS` | `400` | R380 — completion budget of the multi-turn query rewrite (was a hard 100). The Groq slot runs `openai/gpt-oss-120b`, a reasoning model whose hidden reasoning counts against `max_tokens`, so the rewrite truncated on 5/9 multi-turn calls live and every provider in the chain fell through to concatenation. **R381: still accurate — the model is `openai/gpt-oss-120b` again**, see the row below |
| `REGENOLD_DENOISER_MODEL_GROQ` | `default_groq_model()` = `openai/gpt-oss-120b` | **R381 — a P0 was shipped and reverted here.** `f46adb8` hardcoded `llama-3.3-70b-versatile`, which **does not exist on this Groq account**: `GET /openai/v1/models` returns 14 ids and that is not one of them; a POST returns `404 model_not_found`. So every Stage-0 rewrite 404'd and fell through to the 40-turn concatenation — the exact history bleed R380 had just fixed. The same commit also passed `reasoning_effort="none"` explicitly, which **400s** on gpt-oss (`must be one of low, medium, or high`) and is *unnecessary*: `openai_wrapper_provider.py:555-568` already auto-injects the right value per family (gpt-oss → `low`, qwen → `none`). Measured live: no effort 83 completion tokens / 0.6 s; `low` **30 tokens / 0.2 s**. The valid value is family-specific, so never hardcode one at the call site |
| `REGENOLD_DUAL_PASS_RETRIEVAL` | `0` | R380/`f46adb8` — replaces the Stage-0 LLM rewrite with deterministic dual-pass retrieval: pass 1 parses the live user turn (operative provision), pass 2 the prior USER turns only (context anchors, R91: assistant text never reaches entity extraction or BM25), then an ordered dedup fusion. **Default OFF**, and verified so by execution (unset ⇒ 0 `dual_pass_parse` calls; `=1` ⇒ it fires and the fused entity list differs). Registered in `_engine_cache_key`; single-turn is a strict no-op (10/10 byte-identical). ⚠ **Known P0 while ON:** it pre-empts R380's `REGENOLD_DENOISE_SELF_CONTAINED_SKIP`, which re-opens assistant-turn bleed on the wire and drops gold refs — do not flip it on without re-gating |
| `REGENOLD_EXTRACT_SHAPE_GUARD` | `1` | R381 — the R93 `list`/`numeric` extractive pass must produce an answer of the SHAPE the question asks for: a `numeric` answer must contain a cardinal that is not a provision coordinate, a `list` answer must enumerate. On failure it falls back to the lettered limbs of a retrieved provision (`_enumerated_categories`, 29 provisions render cleanly; Annex III correctly renders `None` because its letters restart inside each numbered area) and then to the engine prose. **Closes official-report Q45 (5/5 criteria FAIL) and Q95 (2/2 FAIL)** — both were data fixes that shipped correctly and were then overwritten on the way to the wire by one unresponsive BM25 sentence |
| `REGENOLD_DENOISE_SELF_CONTAINED_SKIP` | `1` | R380 — a self-contained live turn (≥6 words, no coreference, its own anchor) is used VERBATIM as the retrieval query instead of being paraphrased by the Stage-0 rewrite: hard-mode turn 1 becomes identical to easy mode for 100/110 official questions and the rewrite leaves the critical path. Live-only (sits after the no-provider exit), so the cli bench is byte-identical |
| `REGENOLD_QUERY_EXPANSION` | `0` | LLM query rewrite before retrieval (R328 port; latency+cost tradeoff) |
| `REGENOLD_RISK_CLASS_ANNEX` | `0` | Annex-III risk-classification anchor (R328 port) |
| `BEDROCK_REGION` | `eu-central-1` | AWS Bedrock cross-region inference profile geography (R328) |
| `NEO4J_AUTO_SEED` | ⚠ **ON when unset** (given `NEO4J_URI`) | Boot graph seeder safety switch. **Corrected R365 — this table said `0 (or off)` and that is FALSE.** `_auto_seed_disabled_by_env()` (`app/main.py:276-290`) returns `False` when the var is unset, i.e. *not disabled*; its own docstring says “Default is ON when `NEO4J_URI` is set — operators have to opt OUT rather than opt in.” This contradicts `AGENTS.md` (“NEVER set `NEO4J_AUTO_SEED=1` by default”) and `.env.example`. Currently **latent** because production’s `seed_version` matches the code exactly, and R361 hardened the emptiness probe (`app/main.py:550`, `:620-627`) so a swallowed Neo4j failure no longer reads as “graph is empty”. Set it explicitly on Railway: `railway variables --set NEO4J_AUTO_SEED=0`. Flipping the *code* default is confirmation-gated (`AGENTS.md` § Requires Confirmation). |

---

## Parent collapse (R325) — wired in R366, and why it reads +0.0000

⚠ **CORRECTED R366 — `REGENOLD_PARENT_COLLAPSE` was a DEAD FLAG until R366.**
`app/routes/regenold.py` defined `_parent_collapse_enabled()` and
`_collapse_parent_when_subpoint_cited()`, but **nothing in `app/` called
them** — the only importer was `tests/test_r325_parent_collapse.py`, which
exercised the helpers in isolation. Meanwhile the flag table above described
the behaviour as live and `AGENTS.md` drew it as a step in the request
pipeline. Both were false.

**Lost in the port, not intentionally removed.**
`git log -S "_collapse_parent_when_subpoint_cited" -- app/routes/regenold.py`
returns exactly **one** commit — `a659849` ("feat(r328): integrate R320-R328
optimizations") — and that commit adds only the two `def` lines. No commit
ever removed a call site, because one was never added. The sibling repo
`antifragileai-regenold-evaluation` **does** have it, as the last reference
pass. The same port also added
`tests/test_evaluator_batch_july7.py` and `tests/test_r293_july7_difficulty.py`,
which import `evals.regenold` modules it never brought across — those two
still abort `pytest tests/` at collection, so the port was lossy in at least
three places.

**This is the third time.** R329's three rerank placements all read correctly
in the diff and all made zero calls; R330's entire R327 semantic layer never
executed because one call site dropped one argument. The standing rule stays:
default-ON + cache-keyed + unit-tested + documented is **not** evidence a flag
runs. Grep the call site.

**Where it is wired now.** `app/routes/regenold.py`, the LAST reference pass —
after the R276-D1 granularity pass, both clamps, the R260/R311 enforcement, the
R302 pushback freeze and the R365 recall wire guard, and immediately BEFORE the
R50/R131 trace finalisation so the trace still equals the wire refs. That
position is load-bearing: `_collapse_parent_refs` already implements the same
rule mid-pipeline, but it runs immediately BEFORE `_reemit_parents_for_subpoints`
(R87-C, default ON), which re-ADDS the parent — the ordering defect that lets
the wire ship `[Article 50.1, Article 50, Article 50.2]`.

**Order vs the R365 wire guard.** Guard first, collapse second. They do not
fight: the guard is ADD-only and appends a head only when
`_canonical_reference_base` finds no reference carrying that base, so a head
this pass drops (which still has its own leaf, and therefore its base, on the
list) is never re-added. Collapse-second is the safer of the two equivalents.
Both are default OFF, so no interaction ships today.

⚠ **Prove it fires, and expect +0.0000 offline.** The pass is a strict no-op on
the deterministic path: head+leaf clusters are minted live by
`_surface_prose_subpoints` (`_stage2_landed`-gated), and offline the R276-D1
`auto` mode has already resolved every mixed cluster before control reaches the
collapse. Measured across 20 offline questions spanning the sub-point-emitting
topics: **zero collapsible pairs**. So a deterministic +0.0000 is the EXPECTED
reading and is **not** evidence of a broken lever — that misreading is what
killed three R329 rerank placements. `tests/test_r366_parent_collapse_wired.py`
asserts on the wire (call site reached ON, not reached OFF, return value
reaches `response.references`, drop recorded in the trace) and pins the offline
no-op as a **tripwire**: if it fails, the offline path started minting
collapsible pairs and davidath neutrality must be re-measured.

**Gate before flipping it.** It DROPS references — the R142.1 failure mode that
lost a live pairwise judge 11-0 (p=0.001) — and it knowingly overrides the R274
curated-intercept protection (`["Article 6.3", "Article 6", "Annex III"]` →
`["Article 6.3", "Annex III"]`, pinned in
`test_r325_parent_collapse.py::TestKnownTradeIsPinned`). Ship only behind an
`evals.harness.easyhard_ab` win — the gold-bearing harness, **not** `ab_judge`.
