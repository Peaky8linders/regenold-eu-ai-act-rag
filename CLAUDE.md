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

## R446 — the model ids live in a TRACKED file; Fast mode has never engaged

* **Where the model is set.** `app/data/model_config.json` holds `model` (auxiliary
  non-Stage-2 calls), `stage2_model` and `complex_model` (the complex tier, which also
  wins on the standard Stage-2 path). Precedence: env var `P2P_GRAPH_RAG_<FIELD>` >
  the tracked file > the `GraphRAGSettings` field default. To change the production
  model, edit the file and merge to `main`; Railway auto-deploys, so no dashboard
  variable is needed. Fail-soft: a missing or malformed file logs a warning and the
  field defaults apply. Pinned by `tests/test_r446_tracked_model_config.py`.
* **Shipped value (operator directive 2026-09-24):** `claude-opus-5-5` on every Stage-2
  answer. `P2P_GRAPH_RAG_MODEL` does NOT move the answer; the Stage-1 LLM parse it
  names (`_llm_parse_query`) has no caller.
* **Fast mode is blocked by the account, not the wrapper.** Measured on CLI 2.1.280
  with `claude-opus-5-5`: every call sent `fastMode: true` returned
  `fast_mode_state: "off"`, `fast_mode_disabled_reason: "extra_usage_disabled"`. The
  wrapper's `CLAUDE_CODE_FAST_MODE=1` is therefore a no-op, which also explains the
  2026-07-04 "fast mode is a wash" reading. It engages only once extra usage is
  enabled on the Claude account (a billing decision). Check with
  `claude -p --model claude-opus-5-5 --settings '{"fastMode": true}' --output-format json "hi"`
  and read `fast_mode_state`.
* **`REGENOLD_ANNEX_I_RESOLUTION` ships OFF (R446b).** #462's Annex I resolver binds a
  point to the Act the answer names, but the binding is not clause-aware and its generic
  tokens miss the boilerplate every Annex I item shares ("European", "Parliament",
  "Directive"). Measured on the deployed build: "Motor vehicles are listed at Annex I point
  19, whereas the MDR is point 11." moved a correct `Annex I.19` to `Annex I.11`, and a
  Lifts Directive question moved `Annex I.4` to `Annex I.11`. The flag gates both the wire
  pass and the grain deepener's Annex I branch, so OFF is the pre-#462 behaviour. The
  answer-text rewrite (`REGENOLD_ANNEX_I_PROSE_REPAIR`) is OFF for the same reason. Turn
  either on only after an adjacency-based binding clears a paired gate.
  ⚠ **R447: "OFF is the pre-#462 behaviour" is not exact for the deepener.** It still
  applies #462's Annex I first-mention rule and abstains to bare `Annex I` when that
  mention is unusable: 10 of 318 recorded Annex I replays differ from pre-#462, all
  Ref-Strict-neutral.

## R447 — the R446 follow-ups: two fixed routes rewritten, three P2 items cleared

Full record: `docs/measurements/r447/CHECKPOINT.md`.

* **Curated (fixed-route) answers skip Stage-2, so four route rules bind their text.**
  All four bit while rewriting `user_information_transparency` and `role_difference`:
  1. at most 3 sentences;
  2. every sentence carries an `article`/`annex` token;
  3. no `_META_LEAK_SUBSTRINGS` phrase ("obvious **from the context**" deleted a whole
     lead sentence);
  4. mind the ref budget. It is 5 on a plain question and 10–12 on a compound-role or
     scenario phrasing. R87-C re-emits each leaf's parent head, and R287 then folds
     head+leaves. `REGENOLD_CURATED_KEEP_DECLARED_LEAVES` (below) stops that fold for
     sibling leaves.

  Offline wire before → after: Art. 50 route 464 chars / `['Article 50.1']` → 1185
  chars / 50.1, 50.5, 50.3, 50.4, 26.11. Role route: Articles 16 and 26 gone,
  `Article 3.3, 3.4, 25.1` ship.
* **`REGENOLD_CURATED_KEEP_DECLARED_LEAVES` (default ON).** R87-C no longer
  re-emits a curated intercept's head when the declared leaves under it have no
  dominating member. A bare copy of that head added by another pass
  (`expand_citations` on scenario shapes) is dropped before R287 while its leaves
  are listed. Without this, at budget 10–12 those clusters were folded into the head
  and deepened to ONE paragraph: the Art. 50 route cited `Article 50.4` (deep fakes)
  alone. A blanket skip was measured and rejected: rg_012's `Annex III.8` fold is
  R287's purpose, and conciseness fell 1.00 → 0.33. Sweep of 1,077 curated variants:
  55 changed, 0 worse, 0 on the official 110.
* **F5:** #462's first-mention-stops rule is Annex I only again. Other annexes use R399's
  "first usable mention", plus a guard against a mention the answer rules out. The
  guard counts a negator only within three words of the mention, with no conjunction
  between. A clause-wide first cut read "not an RBI system **and** falls under Annex
  III point 4" as ruled out. Annex I is byte-identical to the shipped build.
* **F8:** the R365 biometric Art. 50 trigger (default OFF) matches per sentence. Another
  sentence counts only as a QUESTION with an Art. 50 duty VERB. Fire-sets are
  unchanged except probe 3 → 2, a row whose gold has no Art. 50.
* **F9:** R442's whole-head answer-length floor is behind `REGENOLD_WHOLE_HEAD_FLOOR`
  (default ON) and is withheld only from a narrow verdict ask: yes/no, with no open
  request in any sentence. A head-as-subject regex was tried first; the review
  measured it losing ordinary phrasings, so it was replaced. 0 answer-shape changes
  on the official 110.
* **Pushback-keep threshold (`REGENOLD_KEEP_MIN_GAPS=2`) scored: NO WIN.** Strict
  correctness is +7.14 pp, CI [−2.38, +16.67], 0/3 samples separating. Ref conciseness
  is −1.03 pp with a CI excluding 0. `REGENOLD_PUSHBACK_KEEP_CONTRACT` stays OFF. The
  draws predate `--require-cohere`, so this is a screen.

## ⛔ R398 — the merge gate itself returned a FALSE GREEN, and the R397 lever was inert

**Executed 2026-09-09.** Two defects in the *instruments*, not in the product. Both are the
R329/R330/R366 shape one level up: the thing that was supposed to be measuring was not running.

### 1. `easyhard_ab` printed PASS on runs where Stage-2 never landed

The gate AGENTS.md invariant #5 mandates for every prompt-side lever had **no liveness guard**.
Offline (`P2P_GRAPH_RAG_PROVIDER=cli`, dead `OPENAI_API_BASE`) both arms return the same
deterministic Stage-1 answer, the three prose→refs passes are skipped at their `stage2_landed`
route call sites, `gold_dropped_head` is identical by construction — and the gate printed
`PASS`, exit 0. Reproduced on `1dc70db` at n=6 **and at full corpus**:

```
BEFORE  easy n=95  hard n=37   delta +0 / +0   ->  "PASS"          exit 0
AFTER   easy n=95  hard n=37   delta +0 / +0   ->  "INDETERMINATE" exit 2
                                    LIVENESS FAILED: no Stage-2 completions landed.
```

**Every historical prompt-side "cleared the gold gate" claim made from a local run is
unverifiable.** R365 turned the flag string into an exit code; the exit code could still be a
false green for a different reason.

`main()` now has **three** outcomes — `0` PASS, `1` hard-rule-#8 FAIL, `2` INDETERMINATE — and
a run is indeterminate when **any** of:

* **no Stage-2 landed** — read from `app.llm.stage2_policy.transport_stats()`
  (`primary_ok`/`fallback_ok`), zeroed before the arms run. ⚠ The first cut of this guard
  imported `app.integrations.regenold.transport`, **which does not exist**, and a bare
  `except Exception: pass` swallowed the `ModuleNotFoundError` — so every `--local` run read
  "not live" whether or not it was. `_transport_liveness` now returns an explicit reason
  string and an import failure is reported as UNKNOWN, never laundered into "not live";
* **a scored split is below `_MIN_GATE_N` (30)**;
* **a split the probe corpus carried scored zero rows** — `_split_gold_dropped` returned
  `None` for an unscored split, which dropped it out of `splits` entirely, so "zero on ANY
  split" quietly became "zero on the splits that happened to score". `easyhard-v2_ab_gate.json`
  (easy 10, hard **0**) and `easyhard-r379-promptv2-bedrock.json` (n=132) sat on disk for the
  **same flag**, one PASS one FAIL, with equal standing. A run scoped with
  `--multiturn only|skip` is not penalised — `expected_splits` is what the corpus actually held.

⚠ **`_MIN_GATE_N = 30` buys HONESTY, not POWER — do not cite it as power.** The recorded
resolution threshold for the reference axes is **n ≥ 120** (R367), and R381's cap=3 simulation
read PASS at n=17/30/34 and FAILED at n=129, so 30 is a value at which the record shows a
*wrong* verdict. It cannot be raised: **the probe corpus tops out at easy=95 / hard=37**
(measured), so any floor above 37 makes the gate permanently indeterminate. Its whole job is to
reject smoke runs. `--allow-gold-drop` suppresses a FAILURE only; indeterminacy is a statement
about the evidence, not about what the operator will accept.

⚠ **And the gate must never die of an encoding error.** A `⚠` in the new verdict prints raised
`UnicodeEncodeError` on a cp1252 console, killing the run **before the sidecar was written** —
and an uncaught crash also exits non-zero, so it was indistinguishable from a hard-rule-#8 FAIL.
Gate output is ASCII; both streams are reconfigured with `errors="replace"`.
`test_the_gate_report_is_cp1252_safe` pins it.

### 2. `REGENOLD_COORD_MAP_PROMPT` was a DEAD FLAG — the fifth instance

`_valid_coordinate_line` (R397) had exactly one call site, inside `_llm_generate_answer`,
**which has no production caller** — the repo's own comment at `_graph_rag_impl.py:7625` says
so. Spy-instrumented through the real route with Stage-2 landing: **Stage-2 called, the builder
called 0 times.** The R397 hypothesis (tell Stage-2 the real coordinate range, attack Ref
Strict) is therefore **untested, not disproven**, and the reported "7/20 vs a 6/20 noise floor"
compared two byte-identical prompts.

**And the test written to prevent exactly this was a source-string search** —
`assert "user_message += _valid_coordinate_line(context_text)" in source` — satisfied by a line
in a function nothing calls. Measured in the dead state: the old assertion evaluates **True**
while the new call-count test **fails**.

Now wired into `_claude_max_enhance_answer` (the real Stage-2 path), fed the reference block.
**Verified by call count and by the dispatched bytes**, two-sided:

```
flag OFF, compact OFF   calls=1  "VALID COORDINATES" on the wire: False
flag ON,  compact OFF   calls=1  "VALID COORDINATES" on the wire: True
flag ON,  compact ON    calls=2  "VALID COORDINATES" on the wire: True   (was False)
```

⚠ **`REGENOLD_PROMPT_COMPACT` REPLACES `user_message` wholesale** (`~:9479`,
`build_compact_answer_user`), so it silently discarded the coordinate map — the lever switching
itself off in one of the two arms an A/B would compare. R391 had already had to re-append the
pushback clause for this exact reason. **Anything appended above that line must be re-appended
inside the compact branch.** Still default OFF; the A/B is now meaningful for the first time.

### Still open, deliberately (reference levers need the live gold gate)

* **The two prose→refs guards are asymmetric, and both errors inflate the emitted count** —
  against Ref Conciseness, the highest-leverage axis. Reproduced: the ADD pass's
  `_CONTRAST_BEHIND_RE` is behind-only with a ≤4-word window, so
  `"Article 5 is not engaged here."` **promotes Article 5** and `"This is NOT the EU-database
  annex, that is Annex VIII."` **promotes Annex VIII** (the live R379 mechanism), while
  `"This is not Article 5."` is correctly suppressed. The DROP pass
  (`_reference_described_in_prose`) has **no negation check at all** and is number-anchored, so
  a paraphrase drops a reference while an explicitly ruled-out provision is kept.
* **Seven prompt-side levers ship default ON with no `gold_dropped_head` record** —
  `REGENOLD_USER_CRITICAL_RULES`, `REGENOLD_ANSWER_COVERAGE` and the other default-ON
  user-channel clauses. `git ls-files docs .planning evals | xargs grep -l` returns **0 files**
  and no sidecar carries them. This is what R379 caught PR #368 doing. Gate them **after** the
  liveness guard exists, i.e. now — a pre-R398 run could not have measured them.

Full evidence: `docs/reviews/r398-invariant-5-audit-2026-09-09.md`.


## ⛔ R442 — PRs #456–#460 audited by execution; R440's verdict is VOID; Opus 5.5 option

Full record: `docs/measurements/r442/PR-AUDIT-456-460.md`, `OPUS55-SCREEN.md`.

* **R440's "NO WIN — powered null" is void.** The harness wrote `"void": ["hard"]`
  and arm A sample 0 carried 13 fallback-served rows, which PREFLIGHT §4 forbids
  (without them the binding conciseness cost is −0.88 [−4.27, +2.11]); and the ON
  arm handed `_grounded_branch_guard` the FLATTENED conversation, so the hard
  preamble fired all 11 blocks (5,611 chars) on every row. The guard also misstated
  Art. 5(1)(g), 6(3), 26(6) and 80(2) and echoed two of our own gold criteria.
  Rewritten (live question only, word-bounded triggers, one block per branch,
  verbatim-checked law). `REGENOLD_GROUNDED_BRANCH_GUARDS` stays default OFF as
  **unmeasured**; a verdict needs a fresh draw under PREFLIGHT §4.
* **R439's `engaged_coords` head rule is scoped back to heads.** It withheld the
  list of a named paragraph (6(3)(a)–(d), 9(2)(a)–(d)) while ANSWER SHAPE told
  Stage-2 not to enumerate outside the engaged set; a whole-head ask with nothing
  engaged now takes the R423.1 no-signal floor. Official 110: the only answer-shape
  change is `rg_105` 375 → 650 target chars (reference answer 625).
* ⚠ **PR #456's compact REFERENCE MINIMALITY / SUB-PARAGRAPH clauses are default
  ON and ungated** (+441 chars per Stage-2 request, invariant #5). Left as the
  operator merged them; gate with `REGENOLD_USER_REF_MINIMALITY=0
  REGENOLD_SUBPARAGRAPH_ATTRIBUTION=0` as the baseline arm before relying on them.
  On the evidence-contract path `REGENOLD_PROMPT_V2/V3/COMPACT` are dead flags.
* **The R440 owner lock did nothing across Windows consoles**: `os.kill(pid, 0)` is
  `GenerateConsoleCtrlEvent` there, so a runner in a second terminal acquired over
  a live draw. `evals/regenold/run_lock.py` holds an OS byte-range lock instead.
* **Opus 5.5 over the tunnel** = `P2P_GRAPH_RAG_COMPLEX_MODEL=claude-opus-5-5`
  (wins on every Stage-2 call). Requires Claude Code **≥ 2.1.280** on the wrapper
  host — 2.1.269 answered `400 … does not support this model`. The eval preflight
  now probes each arm's EFFECTIVE model (`effective_stage2_model()`); it used to
  probe `stage2_model` once, before any arm env, so a model A/B never probed its
  branch arm. Live screen (8 easy rows, 5 discriminating): correctness identical,
  answers 841 → 1050 chars, Overall 80.6 → 79.8 (Sonnet 5 judge). Default unchanged.
* **Open, needs an operator ruling:** RESERVE — re-serve the verified previous
  answer on the evaluator's verbatim pushback (Speed 79 → 95, ≈ +2.1 pp Overall
  locally) contradicts the "always Stage-2" rule and drops gold heads on two replay
  pools as specified. Not built.


## ⛔ R431 — the sibling-limb deficit is ATTRIBUTION, not generation. The wire gets an ADD.

Full evidence: `docs/measurements/r431/CHECKPOINT.md`. Artefacts: `sibling_triage.py`,
`add_threshold_sweep.py`, `wire_add_probe.py`, `wire_add_gate.py`.

**R429's handover was wrong, and re-measuring it is the whole finding.** R429 closed
by naming the next lever as *"135 of the remaining unmet gold sub-points name a sibling
limb the prose doesn't name either — that is generation-side prompting work"*.
Measured per draw (`sibling_triage.py`, today's board): of **173** unmet gold
expectations, **85** are `named_sibling_on_wire` — the prose **does** name the gold limb
and the **wire** ships a sibling of it (`rg_100` names `Article 6.1`, `6.2` and `6.3`,
ships only `6.2`). Only **50** are "the prose names neither", the genuinely
generation-side set. Per ROW the effect is smaller still: of 28 rows with a landed draw,
16 are met in every draw, 11 are draw-dependent, **5 are structural**.

The pass abstains there **by contract**: `_ground_wire_subpoints` is 1:1 in place, so
when the prose names the wire's limb *too* it cannot add the missing one.

**The repair — `REGENOLD_GROUND_WIRE_ADD`, default ON.** `_ground_wire_add_missing`
appends the prose-named limbs the wire lacks, only when the parent is already on the
wire (so the folded head SET, and Ref. Loose, cannot move), only for coordinates
`coordinate_exists` admits, and only when **both the answer and the question** discuss
the limb's *own* statutory text above calibrated floors.

**The floors are a measured TARIFF, not a guess.** Ref. Strict can only gain and Ref.
Conciseness can only lose, so the operating point is points-of-strict per
point-of-conciseness. Swept on 554 recorded rows with the real rubric: the **unfiltered
ADD is net NEGATIVE** (501 additions, 23.6 % precision, ΔStrict +8.84, ΔConc −7.49 →
**−0.80** implied Overall) and the whole `q = 0.0` column never reaches the plateau
even at a 0.9 answer floor (+0.14). The optimum is a **plateau** — `(0.5, 0.4)`,
`(0.6, 0.4)` and `(0.7, 0.4)` all tie at **+0.32** — and the default `(0.6, 0.4)`
sits on it.

**Measured effect** (`wire_add_probe.py`, 554 rows, real rubric): Ref. Strict 73.13 →
**76.90 (+3.76)**, Loose **+0.00**, Conc 40.78 → 40.17 **(−0.61)**. R419 board only:
Strict 65.15 → **70.45 (+5.30)**, Loose +0.00, Conc **−0.86**. 53 rows fired, 53
coordinates appended, 35 gold (66.0 %). Construction guarantees **asserted per row
rather than argued**: **0** folded-head-set violations, **0** Strict regressions, max
append 1/row (cap 2). The head invariant is a **SET** invariant, not a multiset one —
`reference_correctness_loose` reads `set(_heads(pred))`, and asserting multiset
equality reported **53 false violations**, every one a correct append under a head
already present.

**Live gate: 9/9 criteria PASS, `SHIP`** (`wire_add_gate.py`, verdict in
`docs/measurements/r431/gate-verdict.json`). 27 comparable hard rows across **three
independent generations**: Ref. Strict 80.86 → **84.57 (+3.70)**, Loose **+0.00**, Conc
**−0.12**. The lever fired on 3 rows and appended 6 coordinates, **all 6 of them gold**;
Ref. Strict moved up on 1 row and down on none; **0** folded-head-set violations, **0**
met→unmet regressions, gold heads dropped unchanged at 0. The first wrapper-backed attempt
was incomplete at 12/37 and is retained as provenance only; after Bedrock was restored,
the completed 37-row × 3-generation draw finished on an alternate transport with the
same Stage-2 model identity, and the reader uses all three complete generations
(`repeats: 3`). The tolerance criteria were not relaxed. **Two silent reader
defects were found and fixed by this run rather than by the numbers** — the first version
checked the derivation licence over rows the pass never owns (the deterministic-leg rows:
out of scope, not a lever fault), and drove the pass with `question=""`, which zeroes the
ADD's second vote and reported the lever inert on 27 of 27 rows. Both are recorded in
§4.3 of the checkpoint because the non-vacuity and licence criteria are what caught them,
not the axis deltas.

**The transport guard is now LEG-AWARE (R431), and this was the round that exposed why it
had to be.** `_install_stage2_transport_guard` used to abort whenever the PRIMARY tripped
— but the guard was written to prevent one specific outcome (a batch graded on
deterministic Stage-1 drafts), and a tripped primary with a *healthy fallback* is not
that outcome: the wire is still Stage-2's and every row records its leg. Now the
preflight probes the **fallback** (`bedrock_client.check_connectivity_and_permissions`,
which walks the same chain the fallback leg dials) and proceeds as a loudly-labelled
fallback-served draw when the primary probe fails; the mid-run guard reads each row's
`stage2_served_by` and, with the primary tripped but the row fallback-served, warns once
and carries on; it still aborts when **neither** leg answers. Pinned by
`tests/test_r431_fallback_leg_guard.py`. Consequence to know: in an environment where
the wrapper is down and the Bedrock bearer token has expired, both legs are gone and the
run still aborts — correctly — and the checkpoint says so.

**Two repairs of the substitution arm were built, measured and REJECTED** — recorded
in the code beside the function so they are not re-proposed as obvious wins. The defect
they target is real: on `rg_085` the substitution replaces the wire's `Article 6.2`,
**which is the gold key**, with `Article 6.1` — 11 gold keys destroyed across the corpus
(a Hard Rule #8 violation). But:

* **question-grounded veto** (abstain when the question relies on the limb) — at its
  only firing floor (0.2–0.3) Ref. Strict falls **0.61 pp net**: it suppresses 43
  substitutions that were winning to recover those 11. At 0.4 it **never fires**, because
  `q_recall('Article 6.2')` is **0.333**. Inert-or-negative, verified against the
  implementation rather than a model of it.
* **keep-and-add** (append the sibling instead of replacing) — Strict **+0.74**,
  Conciseness **−4.18** across 318 converted slots → **−0.87 pp implied Overall**.

So R425's in-place replace stands and the `rg_085` loss is its price. A repair needs a
signal separating that row's limb from the 43 winning substitutions; **the prose and
the question both fail to** — recorded as an open, characterised limit rather than
papered over.

Also fixed here: the R425 trace reported only positional rewrites (`zip` truncates at
the shorter list), so an **append left the trace silent while the wire had changed**.
It now emits `+Article 6.1` entries.


## ⛔ R432 — the outage remedy had to be made SAFE and FAITHFUL before it was usable

Full evidence: `docs/measurements/r432/CHECKPOINT.md`.

Use a working transport directly when the tunnel or its Max quota is down — that is the
instruction, and following it exposed two defects in the path that is supposed to make it
possible. **Neither is hypothetical; both were reproduced before being fixed.**

**1. The transport allowlist was doubling as the Cloudflare service-token allowlist.**
`_cf_access_trusted_hosts()` (R365) anchored the secret scope on
`stage2_policy.allowed_primary_hosts()` — the list edited via
`REGENOLD_STAGE2_PRIMARY_HOSTS` to point Stage-2 at another transport. So the one knob an
operator sets to recover from an outage also **handed that host the Zero Trust
service-token SECRET**: measured on the R365 code,
`_resolve_cf_access_headers("https://openrouter.ai/api/v1")` returned
`{'CF-Access-Client-Id': …, 'CF-Access-Client-Secret': …}` whenever the allowlist named
that host. Routing policy and credential policy were sharing an answer; they are separate
now — scope is `CF_ACCESS_HOSTNAME` when pinned, else the hardcoded default wrapper host,
and the transport list cannot widen it. Renaming one's own tunnel still works by pinning
`CF_ACCESS_HOSTNAME`. The R365 test that had encoded the leak is inverted
(`TestTransportAllowlistIsNotASecretAllowlist`).

**2. The remedy could not deliver the same model, and failed SILENTLY.** Every model the
app sends is a bare vendor name (`claude-opus-5`); a namespaced transport requires
`anthropic/claude-opus-5` and answers **HTTP 400** — after which the engine quietly serves
a deterministic Stage-1 draft rather than raising. **`REGENOLD_WRAPPER_MODEL_PREFIX`**
(default `""`) now namespaces `claude*` models at the single choke point
(`resolve_wrapper_model`), so Stage-2, the denoiser, the intent classifier and the
preflight all agree. It is scoped to `claude*` on purpose: this provider class is reused
for Groq / Gemini / Mistral, and a blanket prefix would rewrite their ids into nonsense.
It supersedes the alias table, which repairs a name *for the wrapper* — against another
namespace its targets are simply wrong. Separately, the **eval preflight now probes the
configured Stage-2 model** instead of the request default: it had been sending the literal
`claude-opus-4-8` on the premise that the alias map resolved it to "the same effective
model the engine's Stage-2 calls land on", which has been false since R308 turned that map
off, so the probe could pass or fail on a model no row uses.

**Measured after.** Provider seam on the alternate transport: `anthropic/claude-opus-5`
→ HTTP 200 in 4.0 s, **zero** CF headers on the wire. Preflight:
`Stage-2 transport preflight OK (model=anthropic/claude-opus-5)`. A resumed hard draw
records `stage2_served_by=primary`, `stage2_model=anthropic/claude-opus-5`,
`stage2_polish=true` — the same model id as the board, on a different serving route. The
operator's refreshed Bedrock key restores the native fallback leg too
(`check_connectivity_and_permissions → status ok`), so both recovery paths are live.

**One axis this cannot preserve: latency.** The alternate route has no Max-subscription
fast path, so a draw taken this way is comparable on the model axis and **not** on
`resp_speed`. Any speed figure from such a draw is a transport figure, not a production
one. Pinned by `tests/test_r432_transport_remedy.py`.


## ⛔ R428 — the R426 (SOTA legal-KG) round, audited by execution

Full evidence: `docs/reviews/r428-cr-dispositions.md`, artefact
`docs/measurements/r428/dotted_subpoint_probe.py` (630 recorded hard draws, real
passes, real `evals.official.rubric`, no live calls).

* **Three of R426's four headline claims did not survive measurement.** Dotted
  sub-point ADD: **Ref. Strict and Ref. Loose moved on 0 rows**, Ref. Conciseness
  −0.01 pp, and **0 of the 223 unmet gold sub-point expectations** recovered. So it
  is not "the root cause of the −10.3 pp Ref-Strict deficit" and the ADD is **removed**
  (the dotted form stays with `_prose_named_subpoints` → `_ground_wire_subpoints`,
  which rewrites 1:1 and is count- and head-invariant).
* **`REGENOLD_ONTOLOGY_CITABLE_EXPANSION` is back to default `0`.** Its only consumer,
  `REGENOLD_CITABLE_BASE_GUARD`, defaults OFF (R401 rejected it), so at default settings
  the expansion was computed twice per request and thrown away; where it does fire it
  unblocks 191 references of which **1** is gold and **190** excess.
* **The 17 shadow `Article` nodes and their 148 edges are real, and reading them is not
  what unlocks them.** Aura: 125 `REQUIRES` + 23 `APPLIES_TO_ROLE`, all outgoing from the
  shadows; `PROHIBITED_UNDER` / `TRIGGERS_HIGH_RISK_UNDER` / `HAS_OBLIGATION_ARTICLE` /
  `APPLIES_TO` are all **0** on them, and **no live query reads either edge type**. The
  widened `_DEONTIC_CYPHER` MATCH is therefore a canonical-missing **compat shim**: it
  returns 10 rows where the unwidened returns 10 (the projection collects into aggregates
  keyed on `cite`, so twins merge — pinned by a test).
* **Two real bugs, both fixed.** `_DEONTIC_CYPHER` applied the shadow-only id transform to
  every matched node, so `substring('article_6', 3)` rendered **"Article icle_6"** into the
  Stage-2 context for any node without `strict_citation`; and the seeder bridge matched
  `APPLIES_TO_ROLE` in the **reversed** direction (incoming count is 0, so it copied
  nothing and would have written an unused arc).
* **NEVER mirror `REQUIRES`.** It is the R99.1 drift edge — schema says unseeded, R427.1
  removed the mirror, and a test now pins the refusal.
* **Where the Ref-Strict deficit actually lives** (classification of all 223 unmet gold
  sub-points, corrected mid-round after a first classifier folded "parent present at a
  shallower grain" into "parent absent"): **138** name a parent the wire ALREADY carries,
  but only at a shallower grain (`Annex IV.1` on the wire, `Annex IV.1.e` in the gold) — a
  **depth** problem, i.e. R386's deepener remit, and R425's rewrite deliberately abstains
  because a prefix is depth, not substitution; **79** are never named in the prose at all
  (generation-side); **4** are R136's deliberate minimal-cover trade; **2** are a genuine
  coverage gap. So another round of reference post-processing *at the wrong depth* cannot
  move this axis — the lever is the deepener, not another surfacing pass.
* **`ci.yml` has no lint job**, which is how 37 ruff errors reached `main`. The files this
  round touched are now ruff-clean.

## ⛔ R429 — the wire coordinate is COMPLETED to the grain the prose names

Full evidence: `docs/measurements/r429/CHECKPOINT.md`, offline instrument
`docs/measurements/r429/wire_depth_probe.py` (no live calls), live gate
`docs/measurements/r429/wire_depth_gate.py`.

* **R425 abstained on a premise the rubric's own source falsifies.** R425 decided
  that a prefix relation is *"depth, not substitution ... rewriting it would replace a
  graded coordinate with a deeper one **the evaluator may not key on**"*. But Ref.
  Correctness (Strict) is recall of the expected coordinates and
  `rubric._is_descendant` is `pred == expected or pred.startswith(expected + ".")` — a
  prediction **more precise than the key satisfies the key**. So completing
  `Annex IV.1` → `Annex IV.1.e` is monotone on Ref. Strict and **free by construction**
  on the other two: Ref. Loose scores through `ref_head` (parent unchanged) and Ref.
  Conciseness is a pure COUNT ratio over a 1:1 in-place rewrite.
* **`REGENOLD_GROUND_WIRE_DEPTH` is default ON.** `_grain_relation` replaces R425's
  boolean with `same` / **`coarser`** (the R429 population) / `finer` / `sibling` (the
  R425 substitution population); `_grain_compatible` survives as the boolean summary.
  The completion candidate must be named by the answer's own prose AND admitted by
  `coordinate_exists` — it is never minted, so it cannot repeat R386's measured 77 %
  coordinate accuracy (that pass guesses from token overlap; this one only promotes a
  coordinate the prose already used).
* **Two defects in the first draft, both caught by measurement, not by reading the
  diff.** (1) An early `break` on an exact-grain match suppressed a deeper completion
  the prose also named (`rg_070` ships `Article 6.1` while its prose names `6.1` AND
  `6.1.b`): removing it took completions from 79 (**15** gold) to 162 (**78** gold) and
  the delta from +3.14 to +3.77 pp. (2) The tie-break between several prose-named
  descendants is a free bet (any rival is a descendant of the coordinate it replaces),
  so it is spent on the **R425 doctrine** — answer-token overlap with the rival's own
  provision text — which picks the max-gain rival **18/18** on the 18 deciding cases,
  against 13/18 for question overlap and 3/18 for the lexicographic-first rule it
  replaced. ⚠ 18 cases and six rules compared on them: the mechanism justifies the
  pick, the sample does not prove it.
* **Offline, paired on 477 recorded hard draws with a landed Stage-2** (the 153
  deterministic rows are excluded because the route gates this pass on
  `_stage2_landed`): Ref. Strict 65.55 → **72.68 (+7.13 pp)**, Ref. Loose and Ref.
  Conciseness **+0.00**, count and folded-head-set violations **0**, and **0 rows**
  where any expectation went met → unmet — asserted per row, not argued. R425's own
  already-shipped effect on the same board is +0.63 pp.
* **Live gate: 9/9 criteria PASS, `SHIP` (default stays ON).** One live arm, 37
  strided hard rows × 3 independent generations = **111 fresh live draws**, artefact
  `docs/measurements/r429/gate-verdict.json`. Ref. Strict **69.75 → 73.46 (+3.70 pp)**,
  Ref. Loose and Ref. Conciseness **±0.00**, 25 coordinates completed (15 gold), 0
  count/head violations, 0 met→unmet rows, gold heads dropped 1 → 1. Answers are
  PROVEN invariant across arms rather than re-judged — the pass runs after
  `_stage2_landed` and edits only `references`, so the reader asserts byte-identity
  and closes the answer axes by construction. ⚠ The CI is **[0.00, +11.11]** because
  exactly one of 27 comparable rows moved: the direction rests on
  `rubric._is_descendant` (a deeper prediction satisfies every expectation its
  ancestors did), not on this CI.
* **What it does not reach, so the next round does not re-derive it:** of the 207 unmet
  gold sub-point expectations on today's board, 63 are a coarser wire coordinate (34
  reachable and **all 34 now converted**); **22 are a BARE HEAD on the wire**, which is
  R386's deepener / R133's add remit and deliberately out of scope here; 7 have no
  prose-named descendant to complete to; 135 name a sibling limb (R425's population,
  and the prose does not name the gold limb either — generation-side); 9 have no
  coordinate of the parent on the wire at all.
* **The 138-depth number in § R428 is now 86**, because the completion repairs those
  before that classifier sees them. The R428 probe's own conclusions still reproduce
  unchanged (every R426-ADD delta is +0.00).

## ⛔ R410 — the R409 defect set, fixed and re-verified on the wire

Full evidence: `docs/reviews/r410-session-handoff.md` §6. Instrument:
`docs/measurements/r409/r410_wire_probe.py` (offline `TestClient`, asserts the
Part II expectations on the shipped prose + refs).

* **A polar opener is cap-droppable, and that silently deletes the answer.**
  `normalise_answer_for_regenold` drops the longest sentence with no
  `art.` / `article ` / `annex` token until the reply fits its soft cap (code
  default **400**, Railway **1200**). "The EU AI Act does not establish ..." is
  exactly that shape, so the guiding-principles reply shipped the Recital-27
  enumeration **alone** — it asserted the principles existed and lost 2 of the 4
  graded criteria. **Rule: every sentence of a curated answer must carry a cite
  anchor**, so the cap has nothing it may drop at any cap value.
* **Art. 5(1)(g) does not prohibit biometric categorisation as such** — only
  categorisation that infers a CLOSED-LIST attribute (race, political opinions,
  trade-union membership, religious/philosophical beliefs, sex life, sexual
  orientation). The gatekeeper matched the bare keywords `sort patients` /
  `biometric categorisation`, shipping an Art. 5(1)(g) verdict for clinical-trial
  triage. It now requires the closed-list qualifier. **`sex` is NOT on that
  list** — "infers sex" resolves to Annex III(1)(b) high-risk, never the ban.
* **Annex III point 5(d) reaches emergency calls/triage, not clinical-trial
  selection.** `medtech_triage` matched `sort patients ... clinical trial` and
  hard-routed four different Part II facts to one identical emergency-dispatch
  answer; it now requires an emergency-response marker.
* **Conciseness is bought by the repair budget, not by prose.** The R409
  acceptance bound was `max(1.8x, +900)`; answers ran 1.78x and Answer
  Conciseness fell 92.45 → 69.88 pp. `repair_char_budget` is ADDITIVE in the gap
  count (120 + 90/item, ≤1.6x). Prefer shipping the concise original over a
  marginal completeness gain.

## ⛔ R409 — the R408 Gemini commits, audited by execution

Full evidence: `docs/reviews/r409-r408-audit-2026-09-11.md`.

* **The R408 KG "point traversal fix" evicted Article text.** One global `LIMIT` under
  `ORDER BY cite` ("Annex" < "Article"; Annex III = 24 rows = the budget) removed every
  Article's point text whenever Annex III was cited: 42/97 R407 rows on live Aura. Its test
  mocked the function under test and passed on the pre-fix file. R409 keeps ref order and
  shares the budget (`kg_context._allocate_units`): 0/97. ⚠ The block grows 341 → 3,832
  chars/row and is **ungated** (invariant #5), so it now rides `REGENOLD_KG_POINT_TEXT`
  (R416 — **default ON on single-turn asks, legacy query on multi-turn ones**, and `=0`
  opts back into the pre-R408 query outright; the unconditional default was falsified on
  the hard split, see the flag table).
* **The reconstructed gold had verbatim-provable defects** (rg_037, rg_041, rg_060, rg_068,
  rg_082, rg_110), corrected in place with `_revised: "R409"` and the old values kept under
  `_pre_r409`. `score_arm` now stores `_criteria_sha` with every verdict and refuses a
  legacy verdict for a revised row: before R409 the cache key hashed the answer and the
  judge but NOT the criteria, so an edited criterion replayed the stale verdict.
* **Five answer-completeness levers (R409) ship default OFF**, one per engine-side root
  cause of the triage; see the flag table. All are prompt/generation-side ⇒ gate each on
  `easyhard_ab` before flipping.
* **Never "upgrade" a Bedrock-bound model id without a live call.** `eu.anthropic.claude-sonnet-5`
  still 403s (2026-09-11); the intent classifier and query expansion were reverted to sonnet-4-6.
* **R407's hard 80.7 is judge-dependent.** Sonnet 5 grouped judge on the SAME 110 answers:
  **77.4**, Ans Strict 64.5 (Qwen 81.8); on the R409-corrected gold, Qwen **81.4** / Sonnet 5
  **78.3** (`score-r409-*-corrected-gold-hard.json`). Triage of its 67 failing criteria: 0 judge misreads,
  12 defects in OUR reconstructed gold, 55 engine-side (22 omitted enumerated limbs,
  10 wrong provision, 9 missing condition, 7 post-pushback content loss). And R407's
  Stage-2 was Bedrock Qwen 3, not production. Name the judge AND the Stage-2 model with
  every local number.
* **Hard-mode Resp. Speed was scored on turn 1 + pushback summed, plus a 13 s pacing sleep
  inside the timed request.** Fixed for future runs (`score_arm._graded_latency_ms`,
  `run_official_batch._net_of_pacing`); R407's Speed is not a production latency.


## ⛔ R386 — the reference gap is GRAIN, not precision. And the gate's gold was the blocker.

**Executed 2026-09-06.** Two findings, and the second one retires a whole line of work.

### 1. Ref Loose is ALREADY at parity. It is Ref STRICT that lags — and strict means sub-points.

Read the Aug-25 easy column against itself rather than against frontier:

| | Loose | Strict | spread |
| :--- | ---: | ---: | ---: |
| Answer correctness | 89.7 | 81.2 | −8.5 |
| **Reference correctness** | **89.4** | **68.3** | **−21.1** |

Reference Loose (89.4) is already level with Answer Loose (89.7). The operator ask —
"get ref correctness close to ans correctness" — is therefore **entirely** a Ref Strict ask,
and the rubric defines the two axes as Loose *"at the level of Article and Annex numbers"*
versus Strict *"includes subpoints"*. A 21-point loose/strict spread with a head-level
citation habit is a **grain deficit**, not a precision deficit.

Confirmed from the evaluator's own data. The report appendix prints expected sets for five
questions — seven expected references, and **five carry sub-point grain** (`Article 13.3`,
`Article 7.1`, `Article 6.2`, `Article 111.1`, `Article 50.4`) against two bare heads
(`Annex III`, `Annex X`). **The answer key is ~71 % sub-point. We ship 14.3 %.**

⚠ **Two blind spots hid this, both verified by execution.** Our probe gold carries **0/208
sub-point grain** (R331), and `evals.bench.metrics.reference_correctness_strict` calls
`article_heads` on the *prediction* (`metrics.py:388`) — so **the internal "strict" axis
head-projects and is structurally blind to the axis the official strict measures.** No
instrument in this repo could see the largest reference gap we have.

**`REGENOLD_REF_GRAIN_DEEPEN`** replaces a bare head with its question-and-answer-relevant
paragraph. It is **free by construction, then verified**: `gold_dropped_head` folds both sides
onto heads and says so in its own docstring (*"a MORE precise prediction than gold … does NOT
count as a drop here: the head is covered"*); RefConc is a pure COUNT ratio and the count is
unchanged; Ref Loose is head-level and the head survives inside the leaf. Gate replay over the
full live capture of the gold-bearing probe corpus, n=129, scored with `evals.bench.metrics`:

```
arm                    gold_dropped_head   ref_loose   ref_strict   refs/row
OFF                                  37      0.8346       0.6144       3.03
ON  (284 refs changed)               37      0.8346       0.6144       3.03
```

**Every axis byte-identical while 284 references change** — the signature of a transform that
adds precision without moving a provision. Same shape as parent collapse (R381), **not** the
refuted positional-trimmer family. Thresholds are a **plateau, not a peak**: every setting in
`MIN_TOP` 1–6 × `MIN_MARGIN` 1–4 scores 35.5–37.0 and none drops a gold head, so the gain is
not a fitted parameter (`MIN_TOP` measured entirely inert; kept as a degenerate-case floor).
Coordinate accuracy where judgeable: **77 % (47/61)**, against **4** rows where gold wanted the
bare head — 11.75:1. A wrong coordinate costs nothing, because a bare head misses strict too.

### 2. The minimal-gold probe set — the instrument fix, and the R385 verdict it overturns

R385 closed on a structural claim: *"until the gate's gold is minimal, every reference-precision
lever fails hard rule #8 BY CONSTRUCTION — that is a statement about the instrument, not the
lever."* Four independent detectors (applicability, question-role, discourse cohesion,
retrieval-provenance) then hit the same wall, at head-level gold-drop counts of 14 / 16 / 27 / 10
against a baseline of 0. **So build the instrument, not a fifth detector.**

`docs/measurements/r386/mingold.py` — sonnet-5 over the tunnel, **question-only** (it never sees
our answer, our references, the July-7 references or any judge output, so it cannot rediscover
our own citations), two passes: locate the head against the 126-provision title index, then pin
the paragraph against that provision's verbatim text. Pass 2 is **double-sampled and
INTERSECTED**, because single draws are unstable — three draws of rg_018 gave `['Article 7.1']`,
`['Article 7.1','Annex III']` and `['Article 7.1','Article 7.2']`, and one draw of rg_075 drifted
`50.4 → 50.2`. 11 of 110 rows have no stable key and are recorded as **unstable** rather than
given an invented one.

**Validated against the evaluator's five printed keys**: `rg_046`, `rg_018`, `rg_075` EXACT;
`rg_024`, `rg_105` a subset (it misses a second ref). **Precision 7/7, grain 5/5, recall 5/7** —
it never over-cites, and its bias is toward minimality, which is the right bias for measuring
over-citation.

```
minimal gold   1.20 refs/row    92 % sub-point grain
what we ship   2.69 refs/row    14 % sub-point grain

arm                       RefLoose  RefStrict  RefConc  gold_dropped_head   (n=99)
OFF (as shipped live)         60.0       18.3     54.6                  8
R386 grain deepener           60.0       36.5     54.6                  8   (+0)
R385 qrel prune (REJECTED)    64.7       19.4     61.8                  9   (+1)
deepen + prune                64.7       38.5     61.8                  9   (+1)
```

**The deepener DOUBLES Ref Strict, +18.2 pp, at zero gold cost.** And the R385 prune — rejected
because it dropped **nineteen** gold heads against our non-minimal probe gold — costs **ONE**
against a minimal key, while gaining +4.7 RefLoose and +7.2 RefConc. **The instrument really was
the problem.** That still does not clear hard rule #8, which is literally "drop ZERO more", so
`REGENOLD_QREL_PRUNE` stays default OFF — but it is now an operator decision with a price tag
rather than a lever that fails by construction.

⚠ **Do NOT quote this probe's absolute numbers as official-scale.** Scored on the same run the
report graded (`jul07_refs`), its RefConc reads **38.5 against the printed 50.4** — an 11.9 pp
under-read, because it under-recalls the second expected reference and because the report
excludes unannotated questions. It is a **relative** instrument for comparing arms, which is how
every number above uses it. Its refs/row (1.20) does independently corroborate R381's 1.4
recovered from the appendix.

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
the extra provisions onto the wire, because `_add_prose_named_refs` promotes provisions the
prose names (budget: cap=2 first pass + cap=8 consistency pass + 3 subpoint adds ≈ 13 adds/turn;
see `_CITE_CONSISTENCY_CAP` and `_MAX_PROSE_SUBPOINT_ADDS`). **ONE root cause, BOTH conciseness axes.**

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
* R138 `_add_prose_named_refs` (`:5685`, final pass at `:11015`, `REGENOLD_CITE_CONSISTENCY`
  default `1`) — **ADDS** provisions the prose names, capped at `_CITE_CONSISTENCY_CAP=8`;
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
`P2P_GRAPH_RAG_PROVIDER=cli` and a dead `OPENAI_API_BASE`, so `stage2_landed` is False and the
three prose→refs passes are skipped at their route call sites (gated by `stage2_landed`). **A
deterministic fixture pins reference-neutrality in exactly the regime where the coupling is
switched off.** (The functions themselves are NOT no-ops when called directly — R398 verified
`_reconcile_references_to_prose` drops Article 6 and Article 17 at `provider=cli`.)
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
  parameter (`app/routes/regenold.py:5685`) and **both call sites pass it conditionally**
  (`_citable_base_guard_enabled()`, default OFF → resolves to `None`). Needs only a flag
  flip + gate run — not implementation work. Constraining prose-promotion to the
  retrieval-derived universe can only ever *remove an ungrounded promotion*; it can never
  invent a reference.
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
  gate `REGENOLD_STAGE2_TRUNCATION_GUARD`. **R413 fixed the join, which was a
  GUESS.** The rung asked for the missing TAIL and read the boundary off the
  model's LEADING WHITESPACE, and nothing may assume a completion's leading
  whitespace survives the provider: MEASURED live on the primary leg, the R411
  hospital sentence shipped `... on a hospital websiteArticle 50(1), requiring
  that ...`, and the defect was 17 of 40 rows in the objective grammar
  diagnostic. The prompt now requires a `GAP:`/`CONT:` marker (a TOKEN survives
  the trim) and an unmarked tail joins on a word boundary — two visible words
  instead of one nonsense word. R413 also added rung 0 (an exact ECHO of an
  already-grammatical cut sentence, accepted only byte-identical) and fixed a
  prompt that HEDGED where the provision should be named (rg_034: `... available
  to the Court` was completed as `... would instead derive from ...`, 4/4 → 0/4;
  it now names **Article 100(5)** and its cancel/reduce/increase powers). The
  rung ORDER stays opt-in (`REGENOLD_STAGE2_TAIL_REPAIR_MODE`): re-read on a
  VALID leg (wrapper forced down so BOTH arms are Bedrock, judge
  `eu.anthropic.claude-opus-4-6-v1`, 82 symmetric fallbacks, 39/40 rows
differing) the reordered rungs are a **WASH** — OVERALL 72.7 → 72.9 (+0.2 pp,
  inside 3-repeat noise) bought with `regulatory_tone` −2.5 pp, while
  `ans_loose` +1.5 and `ans_conciseness` +3.0. A wash does not ship, so the
  default keeps the legacy order plus the join fix.
* **R413 — void-run detection in the paired gate.** `evals.harness.gate_validity`
  refuses to report deltas when either arm was served by the FALLBACK transport,
  when an off-contract transport was refused, when no Stage-2 completion landed,
  or when a declared system-slot lever dispatched IDENTICAL system payloads to
  both arms. `easyhard_ab` exits 3 with the deltas WITHHELD instead of printing a
  zero-delta table; system payloads are hashed at the provider seam
  (`OpenAIWrapperRequest.system` — the text the model actually receives), because
  the substitution happens INSIDE `_openai_wrapper_complete_for_graph_rag`.
* **R422 — the transport counters were not enough, and neither was a prefix sample.**
  A paired 19-row hard gate for `REGENOLD_CLOSED_SET_SKELETON` reported
  `answer_chars +560.9` and `stage2_landed_rate +0.5789`; the branch arm was healthy
  while the BASELINE arm ran through a wrapper 500 (`No response from Claude Code`)
  and a Bedrock leg answering `api_key_invalid_403` on all five models, so **13 of
  its 19 rows shipped a deterministic Stage-1 draft**. The transport counters did
  not flag it (a deterministic fallback still yields an answer), so
  `gate_validity.count_deterministic_rows` now reads each GRADED row's own
  provenance (`provenance.stage2_served_by == "deterministic"`, else the legacy
  `stage2_polish is False`) and `assess` voids an arm whose graded rows are
  majority-deterministic; `run_official_batch` wraps each arm in `ArmProbe` and
  withholds the delta, marking the modality `void`. The same runner gained
  **`--stride N`**, applied BEFORE `--limit`: the send order is front-loaded with
  easy rows, so `--limit 40` is 68 % easy against the board's 46 %, which is how a
  skewed prefix produced the R422 reading in the first place.
* **R423 — the need-proportional answer contract.** `REGENOLD_NEED_PROPORTIONAL_CONTRACT`
  (**default ON since R423.2** — flipped by its own paired gate, `r423-need4`; set the
  flag to `0` for the shipped fixed-shape prompt) renders ONE deterministic estimate
  of what a question engages,
  twice: an ANSWER SHAPE clause in the Stage-2 contract (item count, target word
  count, and "members outside the engaged list are context, do not enumerate"), and
  a SCOPED closed-set skeleton (`_render_closed_set_skeleton(engaged=...)` keeps
  every engaged member's lead text and demotes the rest to bare coordinates). It
  answers R422's measurement — corr(gold criteria, our answer length) **+0.11**
  against the reference's **+0.55**, with the skeleton firing on 110/110 rows for a
  mean 5,125 chars. Measured offline before any live spend: the per-row reference
  length is **NOT predictable** from the ask (ridge LOO r **0.10–0.14**), so `items`
  is a monotone FLOOR (`clamp(360, 300 + 75*items, 1000)`, mean 584.8 against a
  649.3 reference mean) and the axis is moved by LEVEL, not shape — projecting the
  gold's own references gives **0.4419** for the real R419 answers (reproducing the
  published board exactly) against **0.897** at this lever's targets. The scoped
  skeleton saves **26,607 chars over 37 rows' refs (ratio 0.403)** while dropping
  **zero** engaged coordinates, and the provider-seam probe confirms the clause
  reaches the wire on both sampled rows that reach Stage-2 at all. Gate:
  `--stride 3 --repeats 3` hard, scored by `docs/measurements/r423/need_gate.py`
  on per-row MEDIANS over 3 independent generations (the R416 lever's entire answer
  movement was 2 criteria of 87, which one draw cannot separate from noise).
  `run_official_batch` gained **`--repeats`** (sample 0 keeps the shipped
  checkpoint path and `--resume` contract; replicas are `.r{K}` siblings carrying a
  `sample` key). Fixed on the way: `--help` was broken for the whole runner —
  `--stride`'s help string carried a bare `%`, which argparse interpolates.
  **The first hard gate ran, was VOIDED by its own guard, and falsified two things.**
  (a) **`--repeats` did not produce independent generations.** The route answers
  from `_ENGINE_CACHE`, keyed on (question, context, history depth, env) — and every
  generation of a row sends the same key, so generations 2..K replayed generation 1
  without dialling a provider. MEASURED (37 rows × 3 generations, both arms): arm B
  was byte-identical to generation 1 on **23/37 rows** at p50 **1.6 s** against
  generation 1's **43.6 s**, and made **73** provider calls across three
  generations of 74 asks each. A median over duplicated values reports a
  draw-to-draw stability the run never measured — the R422 failure shape exactly.
  Fixed by clearing the response cache before EVERY sample
  (`run_official_batch._clear_engine_cache`) plus a `_repeat_independence`
  self-check: the runner warns, and `assess` **voids** an arm whose consecutive
  generations are majority-identical (the ~24 % curated-intercept floor is
  tolerated). Proven live on a 2-row × 2-generation smoke: generation 2 cleared 4
  entries and `rg_004` came back 3144 vs 3480 chars, both primary-served.
  (b) **A fallback leg that answers NOTHING was invisible.** Arm A dialled Bedrock
  **20 times and served 0** (`api_key_invalid_403`) while the verdict said nothing —
  `fallback_ok` is 0 in that shape, so an arm whose tunnel failed repeatedly and
  whose fallback is dead read like an arm that never needed either. `ArmProvenance`
  now carries `fallback_attempts`, `primary_failed`, `refused_by_provider` and
  per-LEG payload attribution (`legs`, `leg_system_lengths`): asymmetric fallback
  pressure across arms is a VOID, symmetric pressure is a warning naming the
  counts, a refusal names its provider (`groq×3`, not "off-contract provider
  attempted"), and the 53 kB system prompt is attributed to the leg that carried
  it instead of being merged into one histogram. The void run's own numbers
  (answer_chars 2171.7 → 1204.9 on the same 37 rows, both arms `claude-opus-5`,
  `fallback_ok=0`) are kept in `docs/measurements/r423/CHECKPOINT.md` §5.1.
  **The corrected run (`--label r423-need2`) was VOIDED too, and this time the
  cause was the tunnel.** Measured from its log: **233**
  `wrapper_call_failed: network_error: [Errno 11001] getaddrinfo failed`, 8
  `[WinError 10065] unreachable host`, 2 read timeouts — **243** calls that never
  left the machine, matching the 243 Groq fallbacks the strict-transport policy
  then refused, after which the dead Bedrock credential left a deterministic
  Stage-1 draft. `getaddrinfo failed` means the wrapper hostname did not RESOLVE:
  the Cloudflare tunnel that publishes it was down. Two more holes came out of it.
  (a) **An arm-level total hid a fully degraded generation.** `deterministic_graded`
  is computed from `sample 0` only, while every published number is a per-row
  MEDIAN across generations — so arm A read HEALTHY (47 primary completions) while
  its generation 3 was **28/28 drafts** at 1083 mean chars against sample 1's 2285.
  `ArmProvenance.sample_deterministic` now carries the per-generation counts
  (`probe.provenance(sample_rows=replicates)`) and `assess` voids a gate when ANY
  generation is majority-deterministic. (b) **90 minutes and 243 calls were spent
  finding out.** The runner now pre-flights the wrapper with ONE real 16-token
  completion before the first row is spent (it exercises DNS + CF Access + OAuth
  in a single call) and aborts the batch after **5 consecutive** Stage-2 failures,
  resetting the streak on any success so a blip cannot trip it;
  `--allow-degraded-transport` is the explicit opt-out for a run that measures the
  degradation path itself. The third run, `--label r423-need3`, is slower by
  design — 27 s to 141 s per row, against the voided run's 24 s median, because
  clearing the route cache per sample turned generations 2..K into real draws
  instead of 1.6 s replays.
  **R423b — a restart no longer costs a generation, and the gate reports all eight
  axes.** Two harness defects made the restart expensive and one made the guard
  wrong: (a) `--resume` was gated on sample 0, so a re-launch re-drew replicas
  that were already on disk (measured: four finished generations, ~1.5 h of live
  provider draws, after a machine restart 2.5 h in). The validator is per FILE and
  a replica file holds each row id exactly once, so replica resume is safe and now
  the resumed launch prints `resuming: 37 complete, 0 pending` and spends nothing.
  (b) The gate's zero-completion rule read only in-process counters, so a resumed
  arm (`primary_ok=0`, `calls=0`, 37 graded rows) was VOIDed as "ZERO Stage-2
  completions" — the guard refused a valid run. `ArmProvenance.rows_served` now
  counts the leg each GRADED ROW names in its own provenance, which is the same
  evidence the per-sample determinism rules already read; the rule still fires in
  the outage it was written for (no row names a leg either), and a row naming the
  fallback leg still VOIDs. (c) The gate judged four axes and published four,
  while the official aggregate is a GEOMETRIC mean over eight — a lever that
  shortens answers and pays for it in reference conciseness or speed would have
  read as a win. `need_gate.official_axes` recomputes
  `evals.official.rubric.score_rows` on exactly the comparable subset, per arm per
  generation, and reduces each axis by a MEDIAN over generations, so the gate
  reports all eight axes plus `overall`, and the ship rule refuses an aggregate
  regression beyond 0.5 pp.
  **GATED — the lever is measured and it KEEPS OFF.** The clean gate (`--label
  r423-need3`: valid, zero fallbacks, zero refusals, byte-identical rates 27 %/24 %
  at the curated floor) ran 37 strided hard rows x 3 independent generations x 2
  arms; 27 rows were comparable (primary-served in ≥2 of 3 generations in BOTH
  arms; the 10 deterministic rows are dropped symmetrically). Result, per-row
  MEDIAN over generations, on that same 27-row subset, all eight official axes:
  `ans_conciseness` **+45.91**, `ref_conciseness` **+20.62**, `resp_speed`
  **+10.37**, `ref_strict` **+5.56**, and **overall (geometric mean) 65.04 → 79.96,
  +14.91 pp** — against `ans_loose` **−4.04** and `ans_strict` **−7.41**. Arm's own
  37-row board agrees (overall 72.76 → 82.33, +9.56). The entire correctness cost
  is **2 of 27 rows** (`rg_010` 2763→379 chars, `rg_106` 2651→442, the latter also
  dropping `Annex III`), both reproducible in every generation, and both a LENGTH
  STARVATION: `rg_010` is "which article governs human oversight" — 4 criteria the
  long answer enumerated — and the shape clause read it as a one-item ask. No row
  improved on correctness, so the pre-registered rule (correctness no worse than
  −1.0 pp) refuses the default. The estimator's item count is the defect: the
  offline calibration already warned (59/110 rows called "1 item" while only 4 rows
  truly have 1 criterion), which is why the next lever is a content-preservation
  contract tied to the Stage-1 draft's own engaged set, not a bigger length target.
  **Scope caveat, measured post-deploy — and CORRECTED in R423.3.** A hard-mode
  request past the first two rows dispatches the **61-char persona**, so this gate
  measures hard mode under the STRIPPED prompt, the configuration R411 gap 3.1
  names. The blanket version of this row ("a hard-mode request dispatches the
  persona") was **FALSE** and is falsified by
  `docs/measurements/r423/graded_scope_probe.py`, which drives real hard rows
  through the real route and records (row, turn, user chars, system chars) per
  dispatch: `run_official_batch._run_hard` keeps a rolling conversation that starts
  EMPTY, so the **first two rows of any run read `history_turn_count` 0 and 1 and
  receive the FULL ~59.6 kB system prompt**. Only from row 3 on does a hard run read
  >= 2. Decisive pair, same row and same harness with only its POSITION varied:
  `--ids rg_004` dispatches `59644` on turn 1, `--ids rg_001,rg_004` dispatches
  `61` for that same turn-1 ask. The engine is right (a request carrying 0 prior
  turns IS a single-turn ask); the claim was wrong — the modality is a property of
  the caller's conversation, not of the benchmark's name. The gate's own payload record shows the asymmetry that
  caused: arm A was **resumed**, so `--resume` restarted its rolling history and it
  made one full-prompt primary dispatch arm B (continuous) did not
  (`A:primary` `61 × 17 · 6365 × 3 · 59644 × 1` against `B:primary`
  `61 × 168 · 132 × 5 · 1311 × 3 · 6365 × 117`; A's `fallback` leg is `59644 × 5`
  because **Bedrock always receives the full ``system``**, R360 — not a Stage-2
  measure). Bounded rather than asserted:
  `docs/measurements/r423/need_scope_sensitivity.py` re-scores the gate's judged
  rows leaving out each of the 27 comparable rows in turn — the overall delta stays
  in **[+13.42, +14.50] pp** against **+13.93 pp** as run, so no single row carries
  the win. The resume defect is FIXED generally:
  `run_official_batch.seed_history_from_records` rebuilds the rolling conversation
  from the rows already on disk, so a resumed hard run sends the same history an
  uninterrupted one would (pinned in `tests/test_r423_3_resume_modality.py`,
  including that a FRESH run still starts empty — that is the shipped baseline).
  Live single-turn already answers `rg_010`
  in the lever's ON shape (316 chars, `Article 14.1`, primary-served, verified
  against production `dd87fd45e3ae`) because it gets the full 53 kB system prompt
  via `REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN=1`. The lever's incremental effect
  on that path is NOT measured and is the next question.
  Report: `docs/reports/r423-need-proportional-gate.md`.
  **R423.1 corrected the ESTIMATOR (not the rule) and re-opened the gate.** Both
  lost rows are rows where the estimator found **no anchor at all** — `asked` and
  `engaged` both empty — and that state is **80 of the 110 rows (73 %)**. So the
  level is not a patch for two rows, it IS the lever on this board. The defect is a
  category error: **empty engagement is ABSENCE OF SIGNAL, not evidence of a small
  ask.** The detector is the R410 question-side rule, strict on purpose because it
  gates a completeness DEMAND (it cut false positives 7/71 → 0/71); strictness is
  right for demanding and wrong for sizing and for forbidding. Three changes: an
  `anchored` flag; a no-signal FLOOR of **650 chars** — the unanchored subgroup's
  OWN central reference length (median 657, mean 646 over the 80 rows, NOT the two
  rows that exposed the bug), costing **−1.22 pp** on `ans_conciseness` over the 23
  reachable unanchored rows and **free below 550**; and the skeleton's
  coordinates-only branch no longer forbidding the provision (the shipped
  prohibition is kept only when the ask engages a DIFFERENT provision — a real
  signal). A **graded** floor was tested and REJECTED: nothing the estimator can see
  predicts an unanchored ask's reference length (corr(ask length, ref length)
  **+0.23** Pearson / +0.16 Spearman; criteria count does, at +0.56, and is not
  available at inference). Live, one generation: `rg_106` **1/3 → 3/3** with
  `Annex III.6.d` back on the wire, `rg_010` **3/5 → 5/5** including `Article 14.4`.
  Evidence: `docs/measurements/r423/CHECKPOINT-r4231.md`,
  `need_floor_projection.py`.
  **R423.2 — `r423-need4` CLEARED the pre-registered rule, so the lever is ON.**
  Hard split, 37 strided rows × 3 independent generations × 2 arms, judged with the
  R419 board's instrument; per-row medians over the **27 comparable** rows (floor 20):
  `ans_correctness_loose` **+0.00 pp**, `ans_correctness_strict` **+0.00 pp** (the
  first gate's −4.04 / −7.41 is GONE), `ans_conciseness` **+38.86**, `ref_correctness_loose`
  **+3.70**, `ref_correctness_strict` **+5.56**, `ref_conciseness` **+12.80**,
  `resp_speed` **+10.77**; answers **−2108 chars**; gold heads dropped **A 1 → B 0**;
  **overall (geomean) 65.62 → 79.56, +13.93 pp**. All five pre-registered conditions
  held. ONE row of 37 (`rg_085`) was excluded from BOTH arms because its transport
  degraded, which is what forced the R423.2 guard fix below.
  **R423.2 also fixed the void guard's granularity** (`gate_validity.assess`, new
  `excluded_rows`). The guard's own warning says a draft row "belongs in the excluded
  set, not averaged over", yet it VOIDED the whole paired run for one — discarding 27
  sound paired rows and five hours of live draws, on a row the gate's comparability
  filter had ALREADY dropped symmetrically. The new argument lets a caller ACCOUNT for
  the rows it excluded: each one absorbs at most ONE off-contract refusal
  (`arm.refused <= excluded_rows`), the set must stay a minority (`excluded_rows * 4 <=
  arm.rows`), and every arm-level rule (zero completions, per-sample determinism, the
  deterministic majority, byte-identical replays, payload identity) is untouched.
  `degraded_row_ids` is the shared definition — a row that NAMES a non-primary leg; the
  route's curated intercepts name NO leg and are NOT degradation (folding them in would
  drop 9 stable byte-identical rows from every pair). `ArmProvenance.from_dict` makes a
  saved verdict re-derivable from its own artifact (`docs/measurements/r423/regate_gate.py`),
  so a guard change does not cost another five hours of live quota on identical rows.
  Report: `docs/reports/r423-need-proportional-gate.md`,
  gate `docs/measurements/r423/need_gate.json`.
  **Also fixed on the way, and it cost a run:** the R423 Stage-2 transport guard
  patched the provider CLASS, so an AUXILIARY leg's failures counted as Stage-2
  transport failures and aborted the gate after four rows on a Groq denoiser `429`
  (`openai/gpt-oss-120b`, whose own chain falls through to Haiku) while the Claude
  leg was demonstrably healthy. The guard now discriminates the leg (`_is_primary_leg`
  — identity against the wrapper singleton, endpoint as fallback) and only the
  primary can trip it; auxiliary failures are counted, reported, and never fatal;
  and the abort names the leg and the failure KIND (`[transport]` vs `[model_side]`).
* **R424 — the hard modality is now the OFFICIAL one (harness default flipped).**
  The official challenge defines hard mode as *"a pre-fixed synthetic 9-turn
  conversation … the actual question being evaluated appears in the 10th turn"*.
  `_run_hard` did not do that: it rolled its own prior Q&A, **starting empty**, so
  row 1 was asked cold and row 5 with four exchanges, and the leading rows read
  `history_turn_count` 0–1 — inside the Stage-2 single-turn predicate — and were
  dispatched the **full 59 644-char** system prompt while every later row got the
  61-char persona. One arm, two system prompts, decided by a row's **position**.
  `evals/regenold/hard_preamble.py` holds the fixture and `DEFAULT_MODE` is now
  **`fixed`**: the same 9-exchange dialogue before EVERY row, so the modality is a
  constant of the run (turn 1 = 18 prior messages, the evaluator's own recorded
  `history_turns_used`, reproduced exactly). `rolling` stays reachable as an
  explicit `REGENOLD_HARD_PREAMBLE=rolling` for reproducing the pre-R424 boards.
  Because the fixture IS the history, the R423.3 `--resume` leak cannot recur in
  this mode. The paired gate (`r424-preamble`, 37 strided rows × 3 independent
  generations × 2 arms, judged with the R419/R423 instrument, 28 comparable rows)
  cleared all four pre-registered conditions: answer correctness **tied at exactly
  +0.00 pp on all 28 rows**, official overall **78.44 → 78.56 (+0.11 pp)**, gold
  heads dropped 1 vs 1, `ans_conciseness` +1.86 / `ref_conciseness` +1.86 /
  `ref_loose` +1.79 / `resp_speed` +0.42.
  **Guard change this forced:** a lever can live in the **request** slot, where
  byte-identical system payloads are the CORRECT outcome — so
  `gate_validity.lever_changes_request` + `REQUEST_SHAPE_FLAGS` and
  `assess(..., lever_slot="request")` check the recorded `request_shape` instead of
  voiding a correctly-built run. The default slot stays `"system"`, so every
  existing caller is byte-identical.
  Record: `docs/measurements/r424/CHECKPOINT.md`, probe
  `docs/measurements/r424/hard_preamble_probe.py` (offline, stubbed provider — the
  dispatch shape is decided before the provider is reached).
  **Open finding carried forward (R425 candidate):** the `ref_strict` −3.57 pp is
  two rows plus one partial, and it traces to a **reference-grain substitution** —
  in 15 arm-row occurrences across 8 rows the graded wire records a neighbouring
  limb of a parent the prose itself sub-points (prose `Article 99(3)`, wire
  `Article 99.4`; prose `Article 3.64`, wire `Article 3.65`). That is a route change
  to the graded `references` field, so it needs its own paired gate, not a bundled
  edit. Evidence: `docs/measurements/r424/refstrict_draw_dependence.py`.
  **ADDRESSED IN R425** (below).
* **R425 — the wire grain is grounded in the answer's OWN prose.**
  The mirror of R133. `_surface_prose_subpoints` ADDS a prose-named leaf when the
  **bare parent** is on the list — so a wire that already carries a **sibling
  limb** never receives the grounded one, and the ungrounded limb ships to the
  graded `references` field: `rg_100`'s answer names `Article 6(3)` and the wire
  recorded `Article 6.2`; `rg_067` names `Article 3(64)` and shipped `Article 3.65`.
  `_ground_wire_subpoints` (`regenold.py:~4490`, default ON via
  `REGENOLD_GROUND_WIRE_SUBPOINTS`, `_stage2_landed`-gated like its ADD twin)
  rewrites the wire limb **in place** onto the limb the prose names, immediately
  after the R386 deepener and the R397 coordinate guard and before every pass that
  can drop.
  **The direction is measured, not preferred.** Over the R424 gate's six
  checkpoints (336 comparable row-samples of real draws, real
  `evals.official.rubric`): 106 substitutions across 20 rows, the wire limb is the
  gold one in **0** of them and the prose-named limb is gold in **15**, giving
  `ref_strict` **65.28 → 65.90 (+0.62 pp)** with `ref_loose` and `ref_conciseness`
  byte-identical and the head set and reference COUNT invariant on every row.
  A prefix relation is treated as GRAIN DEPTH, not a substitution (prose
  `Article 13(3)(b)` against a wire `Article 13.3` is left alone), candidates are
  filtered to `coordinate_exists` so the pass never mints a coordinate the
  Regulation lacks, and an ungrounded sibling that sits BESIDE a grounded limb is
  deliberately left alone (dropping it moves Ref. Conciseness and needs its own
  gate). Hard rule #8 is **+0 by construction**, not by measurement: the rewrite
  stays inside the same parent, so the folded head set is bit-identical.
  Verified end-to-end on the live route: OFF ships `['Article 26.5', 'Article 6.2',
  'Article 73.4']`, ON ships `['Article 26.5', 'Article 6.3', 'Article 73.4']`, with
  the answer, the head set and the count all byte-identical.
  **Guard change this forced — a THIRD slot.** This lever changes nothing the
  transport sees (identical system payloads, identical user payloads, identical
  request shape), so under the two existing slots an inert call site would read as
  a clean null. `gate_validity.WIRE_SLOT_FLAGS` + `lever_changes_wire()` +
  `wire_shape_digest()` + `assess(..., lever_slot="wire")` require the two arms to
  have EMITTED different reference sets; the runner prioritises
  `system > wire > request`, and the default stays `"system"` so every existing
  caller is byte-identical. Measured: the two-row smoke was correctly REFUSED
  (`arms' emitted reference sets were IDENTICAL`) because those rows were answered
  deterministically, where the pass is a no-op by design.
  **The slot then needed a second rule, because "the sets differ" is satisfiable by
  NOISE.** At `--repeats 1` the arms draw independent Stage-2 samples, so their
  references differ even with the lever inert — the exact false negative the guard
  exists to catch. `wire_attribution()` therefore intersects on the ANSWER: the
  record is now `{row: [refs_sha, answer_sha]}` per arm, and a wire-slot run is
  valid only if **at least one row drew the SAME answer in both arms and emitted
  DIFFERENT references** — the only pair a post-Stage-2 pass can produce and
  generation variance cannot. A run whose differing rows all drew different
  answers is VOID with the fix in the reason (raise `--repeats`), not a null
  result. `GateVerdict.wire_attributed` publishes the count.
  **Two instruments, not one board run — and why.** The rewrite cannot change the
  ANSWER, so the two answer axes are invariant BY CONSTRUCTION (asserted on a live
  request) and re-drawing them costs hours to measure exactly `0.00`. What can move
  is the three REFERENCE axes, which are the emitted `references` against gold —
  **no LLM involved**. So the population read is a replay over already-drawn
  samples, where each recorded draw is paired against the pass applied to that
  same draw: a stronger pairing than two independent live arms, because nothing
  varies but the pass. A live paired board was launched first
  (`r425-wiregrain`, 37 strided rows × 3 generations × 2 arms) and **stopped
  deliberately** once that property was established.
  **Live reachability** (`live_paired_read.py`, judge-free, 9 targeted rows on the
  real tunnel; 27 arm-A draw-samples and 11 arm-B ones recorded): the OFF arm's
  recorded wires are still rewritable in **7 of 11** draw-samples and the ON arm's
  shipped wires in **0 of 11** — the per-arm proof that the call site fires, which
  an inert one could not produce (it would leave both arms rewritable).
  Head-invariant 11/11, count-invariant 11/11, and `gold heads dropped` moves
  `30→30` / `33→33` across the pass, both arms: hard rule #8 is preserved by
  construction AND observed. Generation is not a pairing (`A#s0` vs `B#s0` are
  different draws — `answer byte-identical across arms: 0/11`), so the cross-arm
  numbers in that artifact are labelled DESCRIPTIVE and are not quoted as a lever
  estimate anywhere; on those 9 **stress** rows the within-draw counterfactual is
  `+0.00 pp` on all three axes, and the population `+0.62 pp` comes from the
  336-sample replay. The same rows show the guard rule refusing to attribute a
  cross-arm wire difference on generation 0 (0 same-answer rows, 8 draw-confounded)
  — the correct verdict for a sample with no same-draw pair.
  ⚠ **Operational:** the longer live leg (`r425-live3`) was aborted mid-arm-B by
  the runner's own guard after 5 consecutive primary failures
  (`api_status_500 "No response from Claude Code"`) — the wrapper backend stops
  answering while its `/health` still returns 200. The guard refuses to grade the
  rest on Stage-1 drafts (R417), so a repeats-3 live gate needs the wrapper up.
  Record: `docs/measurements/r425/CHECKPOINT.md`; replay probe
  `docs/measurements/r425/wire_grain_grounding_probe.py`; targeted live read
  `docs/measurements/r425/live_paired_read.py`. Substitution attribution is read
  off the pass's OWN output (a positional diff of what it returned), never
  re-derived from its guards — an earlier heuristic enumerated pairs the pass
  considers and then filters, and over-counted.
* **R427 — R426 T1: ONE Stage-2 leg-2 dispatch (`app/llm/stage2.py`).** The leg-2
  (Bedrock) verdict was written **twice** — inside `_try_bedrock_fallback` in
  `_openai_wrapper_complete_for_graph_rag`, and in an inline block in
  `_claude_max_enhance_answer` — and the copies had drifted in three ways that all
  matter: the counter was recorded at different TIMES (the transport copy defers
  the verdict so a discarded answer cannot count as `fallback_ok`, R361; the
  answer copy recorded `ok=bool(text)` the moment Bedrock replied), the EMPTINESS
  rule differed (transport `not text` — so `"   "` ships; answer
  `bool(text.strip())`), and `_looks_structurally_truncated` was applied on ONE
  path only. `dispatch_leg2(text, preset=..., structurally_truncated=...)` now
  returns one `Stage2Outcome` `(text, leg, rejected, ok)`; the text is carried
  verbatim, the recording lives in the dispatch and nowhere else, and the two
  divergences are named presets (`PRESET_TRANSPORT` / `PRESET_ANSWER`) documented
  in one table instead of being implicit in two call sites. **This is a PURE
  MOVE** — no env flag, no answer changes — so it ships on the repo's
  byte-identical replay rather than a scoreboard: 258 inputs (250 recorded board
  answers + 8 branch-keying boundaries) × 3 drives, **774/774 byte-identical** on
  text returned, counter deltas, serve marker and warnings, with each drive's
  dial counts asserted so a call site that never ran cannot read as equivalence
  (the first version reported `answer-site dials [1]` and was refused as VOID).
  The gate is shown to FAIL on the deferred change (`sensitivity.py`: perturbing
  `PRESET_ANSWER` to apply the truncation rule drops it to 770/774 on two
  synthetic boundaries and two recorded answers, then restores by SHA-256).
  **Two findings.** F1: the answer path's inline block is **unreachable today** —
  it needs leg 1 to return `None`, and every leg-1 failure either returns leg 2's
  answer or raises — so the retired duplicate was dead code carrying a drifted
  copy of a policy a future branch change would silently reactivate. F2: 162 of
  the recorded answer fields are shaped like truncations. Equalising the presets
  (T1b) changes **which text ships**, so it is explicitly NOT bundled: it needs
  its own graded gate and must first show it is not redundant with the R357
  tail-repair path. Record: `docs/measurements/r427/CHECKPOINT.md`; differential
  `docs/measurements/r427/t1_leg2_differential.py`; falsification
  `docs/measurements/r427/sensitivity.py`; tests
  `tests/test_r427_stage2_leg2_dispatch.py`.
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

## ⛔ R400 — four levers flipped to DEFAULT ON by operator decision, UNGATED

**Executed 2026-09-09, on the operator's explicit instruction to wire the
optimisations in.** These four now ship ON. **None of them has cleared
`gold_dropped_head`.** That is a deliberate, recorded operator decision, not an
oversight, and it is the thing to re-read first if the next scorecard moves:

| flag | was | why it was flipped | what is NOT known |
| :--- | :--- | :--- | :--- |
| `REGENOLD_EVIDENCE_CONTRACT` | 0 | replaces the competing USER-channel stack R380 measured as the conciseness root cause; 14162 → 3531 chars on a pushback turn with evidence, coordinate map and pushback clause all intact | never scored on any axis |
| `REGENOLD_CLOSED_SET_SKELETON` | 0 | R393 measured only **34.7 %** of closed statutory-set members reach Stage-2 (1340/3863 over the official 110), 86 of 110 questions under half | prompt bulk 1.87x ⇒ Speed cost unmeasured |
| `REGENOLD_COORD_MAP_PROMPT` | 0 | attacks Ref Strict, where the evaluator's keys are ~71 % sub-point against our 14.3 %; R398 rewired it after finding it inert | R397 hypothesis untested, not proven |
| `REGENOLD_COHERE_RERANK` | 0 | R331 placement is load-bearing — `kg_context` readers truncate by LIST POSITION at `max_refs=8`, so order decides WHICH provisions' text reaches Stage-2 | never scored; **sends partner questions to Cohere**; the cross-encoder scores `Article 99` (penalties) at **0.4583** on a transparency question, i.e. it does NOT cleanly reject this corpus's failure class |

⚠ **All four are prompt/evidence-side, so per invariant #5 they are NOT
reference-neutral.** Verified on the dispatched bytes that all four fire
together and that the contract does not clobber the coordinate map or the R391
pushback clause. Verified is not scored.

⛔ **Two levers were NOT flipped, and the reasons are recorded:**

* **`REGENOLD_EVIDENCE_IDF` — SCREENED NEGATIVE.** Live paired, n=20, both arms
  0 errors: `ref_loose +0.0000`, `ref_strict −0.0083`, `ref_conc −0.0438`,
  `kw_recall +0.0167`, **est. Overall −0.67 pp**, and one row newly dropped
  gold `Article 5`. The harness returned INDETERMINATE (n=20 < its n=30 floor;
  the ref axes need n≥120), so this is a reason not to enable, not a refutation.
* **`REGENOLD_CITABLE_BASE_GUARD` — DIRECTIVE RELAXED FOR OPT-IN; DEFAULT ON
  REJECTED LIVE.** R401 explicitly permits the opt-in regime to omit an
  answer-named provision from wire references when retrieval did not ground it;
  `tests/test_r138_bluf_verdict_citations.py` pins both regimes. That removed the
  former policy blocker, but not the performance gate. Full live hard-set A/B,
  n=37/arm, all 37 multi-turn probes, Qwen 3 235B through the Bedrock client for
  generation and legal judging: 24 of 37 paired wire-reference lists differed;
  RefLoose **87.84% → 69.82% (−18.02 pp, 95% CI −28.83 to −8.11)**,
  RefStrict **−3.63 pp** (underpowered), RefConc **+9.61 pp** (95% CI +1.25 to
  +19.12), and `gold_dropped_head` **9 → 19 (+10, VETO)**. The three-reference-
  axis leverage estimate is **−1.47 pp Overall**. Qwen legal-v2 pass-rate deltas
  were answer correctness +0.00 pp, reference correctness +5.41 pp, citation
  faithfulness +0.00 pp and answer conciseness +2.70 pp; all were underpowered
  and cannot override the gold veto. Keep default OFF; `=1` remains an
  experimental opt-in.

**Test-suite consequence.** Nine modules pinned the OFF defaults. Every tripwire
was KEPT and stays two-sided; where a test used `delenv` to MEAN "off" it now
sets `"0"` explicitly, because with the default flipped `delenv` means ON and
the tripwire would silently have become an ON-vs-ON comparison (the R365
defect). Modules pinning the pre-R399 USER message declare
`REGENOLD_EVIDENCE_CONTRACT=0`, the regime they were written for — the same
precedent as R360. All four gates use **deny-list** truthiness so a blank or
unexpected value keeps the ON behaviour, which is the R379 P2-7 defect.

**The one thing to do next:** run `evals.harness.easyhard_ab` with all four as
the branch arm, at n≥30 per split, before the benchmark window.

---

## Environment Flags Reference

| Environment Variable | Code Default | Purpose |
| :--- | :--- | :--- |
| `P2P_GRAPH_RAG_PROVIDER` | `auto` | Selected LLM backend (`cli`, `anthropic`, `openai_wrapper`, `bedrock`) |
| `REGENOLD_STAGE2_STRICT_TRANSPORT` | `1` | R360 Stage-2 transport contract: cloudflared tunnel (Claude Max) primary → Bedrock fallback, everything else refused |
| `P2P_GRAPH_RAG_ENABLE_STAGE2` | `1` | Stage-2 LLM polish master gate |
| `REGENOLD_GRAPH_SEMANTIC_LAYERS` | **`1`** | Constrained sub-provision vector search across the five dark Neo4j vector indexes (paragraphs/points/subpoints of already-cited provisions). R330 flipped default ON → OFF pending measurement; **R403 flipped it back ON after the first properly-paired re-measurement**: n=110 hard, Bedrock Qwen 3 235B both arms, shared fresh judge cache (identical answers share verdicts, so deltas are generation-only). RefStrict **+4.50 pp, 95% CI [+1.00, +9.00]**, RefLoose +2.33 ns, every answer axis CI crosses 0, tone flat, gold-head drops 8→5 (veto passes in the winning direction). Deny-list truthiness; `=0` rolls back | 
| `REGENOLD_SEMANTIC_GLOSS` | `0` | Open-domain definitions/recitals gloss. **Re-measured R403** (n=110 paired, same protocol): the R327.1 rejection reason did NOT reproduce (ref axes flat, gold drops 5→4, ans_loose +1.55 ns, tone 99.1→100 via 1 flip) — but the cost is now measured and significant: resp_speed **−0.95 pp, CI [−1.88, +0.06], McNemar p=0.0015, 72/110 rows slower**. Verdict: HOLD AT OFF — marginal gain, real latency cost. Re-test if a gloss-ON subset gate (definitions only, recitals only) becomes available |
| `REGENOLD_GRAPH_VECTOR_RECALL` | `0` | Additive Neo4j & local SVD vector recall path (R326) |
| `REGENOLD_PARENT_COLLAPSE` | **`1`** | Collapse parent provisions when sub-points are cited (R325). Dead flag until R366 wired it; **R381 flipped it to default ON on a live paired A/B** — n=20 official questions, 40/40 calls wrapper-served, 0 Bedrock. Four rows are ZERO-VARIANCE paired observations (answer byte-identical between arms, so refs are the only change): `rg_013` 5→4 (drops `Article 53`, keeps `53.2`), `rg_025` 3→2, `rg_029` 4→2 (drops `Article 6` + `Annex III`, keeps `6.2` + `Annex III.5.d`), `rg_041` 4→2. All 6 drops are bare parents whose own sub-point survives; the **head set is unchanged on all four rows**, and `gold_dropped_head` folds both sides onto heads (`metrics.py:572-574`), so **hard rule #8 delta = +0, measured**. Lever-only Ref. Conciseness **51.3 → 56.3 (+5.0 pp) = +0.90 pp Overall**. Free on the other two ref axes: Ref Loose scores at HEAD level (the head survives inside the leaf) and Ref Strict INCLUDES subpoints (the leaf is strictly better). `=0` restores the old behaviour |
| `REGENOLD_CITABLE_BASE_GUARD` | **`0`** | Restrict prose-named citation promotion to the retrieval-grounded universe. **R403 re-measurement at full n=110 paired (over R401's n=37) CONFIRMS default OFF, now on statistics rather than an underpowered mean**: RefConc +6.72 pp is real (CI [+3.63, +10.22], p<0.0001) but `gold_dropped_head` 5→7 (rg_067, rg_090) trips hard rule #8's veto, and RefLoose −1.50 / RefStrict −2.00 trend negative with CIs touching 0. Do not re-propose without a gold-drop-safe variant. |
| `REGENOLD_GROUND_WIRE_SUBPOINTS` | **`1`** | R425 — the mirror of R133 `_surface_prose_subpoints`: the ADD pass only fires when the wire carries the BARE parent, so a wire that already held a SIBLING limb shipped an ungrounded one to the graded `references` field (`rg_100` answer names `Article 6(3)`, wire recorded `Article 6.2`). `_ground_wire_subpoints` (`regenold.py:~4490`) rewrites the limb IN PLACE onto the limb the prose names — same parent, same count, so the folded head set is bit-identical and hard rule #8 is +0 by construction. `_stage2_landed`-gated like its ADD twin, ordered after the R386 deepener / R397 coordinate guard and before every pass that can drop. **Measured over the R424 gate's six checkpoints** (336 comparable row-samples, the real `evals.official.rubric`): 106 substitutions on 20 rows, the wire limb is gold in **0**, the prose limb in **15** → Ref Strict **65.28 → 65.90 (+0.62 pp)**, Ref Loose and Ref Conciseness byte-identical. Candidates filtered to `coordinate_exists`; an ungrounded sibling BESIDE a grounded one is deliberately left for a separate RefConc gate. **The prefix (grain-depth) case is now completed rather than abstained on — see `REGENOLD_GROUND_WIRE_DEPTH`, and § R429 for why R425's abstention premise was false.** `=0` rolls back. See § R425 |
| `REGENOLD_GROUND_WIRE_DEPTH` | **`1`** | R429 — the prefix half of the pass above. R425 abstained when the prose names a DEEPER coordinate of the wire's own limb (`Annex IV.1` on the wire, `Annex IV.1.e` named by the prose), reasoning that the evaluator "may not key on" the deeper one. `rubric._is_descendant` (`pred.startswith(expected + ".")`) says it does, so completion is **monotone on Ref. Strict and free on Ref. Loose / Ref. Conciseness by construction** (same parent, 1:1 in place) — `gold_dropped_head` +0 and the count invariant, not merely measured. Full pass order unchanged (surface → collapse → deepener → coord guard → this). **Offline, paired on 477 recorded hard draws with a landed Stage-2** (real `evals.official.rubric`): Ref. Strict 65.55 → **72.68 (+7.13 pp)**, loose/conc **+0.00**, 162 coordinates completed (94 gold / 68 excess), count/head/regression violations all **0**. The tie-break among several prose-named descendants is by answer-token overlap with the rival's provision text (18/18 of 18 deciding cases). **Live gate: 9/9 criteria PASS, `SHIP`** — 111 fresh hard draws, Ref. Strict 69.75 → 73.46 (**+3.70 pp**), loose/conc ±0.00, 0 count/head violations, artefact `docs/measurements/r429/gate-verdict.json`. `=0` restores R425's abstention and is the gate's baseline arm. Registered in `_engine_cache_key`. See § R429 |
| `REGENOLD_GROUND_WIRE_ADD` | **`1`** | R431 — the third arm of the same pass: **APPEND** the prose-named limbs the wire is missing. The two arms above are both 1:1 in place, so when the prose names the wire's limb *too* the pass abstains by contract — and that is where the largest bucket of unmet gold sub-points lives (85 of 173: the prose names the gold limb, the wire ships a sibling of it). `_ground_wire_add_missing` appends only coordinates whose **parent is already on the wire** (so the folded head SET, and Ref. Loose, are invariant by construction), only ones `coordinate_exists` admits, and only when **both the answer and the question** discuss the limb's *own* statutory text above the calibrated floors. **554 recorded rows, real rubric**: Ref. Strict 73.13 → **76.90 (+3.76)**, Loose **+0.00**, Conc 40.78 → 40.17 (**−0.61**); R419 board only Strict 65.15 → **70.45 (+5.30)**, Conc −0.86. 53 rows fired, 53 appended, 35 gold (66.0 %); **0** head-set violations, **0** Strict regressions, max 1 append/row. The floors are a measured TARIFF (`add_threshold_sweep.py`) — the unfiltered ADD is net **NEGATIVE** (−0.80 implied Overall at 23.6 % precision), and the optimum is a plateau `(0.5–0.7, 0.4)` all tying at **+0.32**. `=0` restores the substitution-only pass. See § R431 |
| `REGENOLD_GROUND_WIRE_ADD_MAX` / `_ANSWER_RECALL` / `_QUESTION_RECALL` | **`2` / `0.6` / `0.4`** | R431 — the ADD's cap (clamped to 6) and its two recall floors, all three in `_engine_cache_key`. The question floor is **load-bearing and not luck**: the entire `q = 0.0` column never reaches the plateau even at a 0.9 answer floor (+0.14 vs +0.32), because the answer's own text cannot substitute for the question's — it is the only evidence of what the benchmark's *minimal* gold key is for, and it is exactly what a sibling cannot fake. Lowering `_QUESTION_RECALL` to 0.3 is **falsified** (+0.23 vs +0.32). See § R431 |
| `REGENOLD_STAGE2_TRUNCATION_GUARD` | `1` | R357 post-generation truncation repair on the Stage-2 polish |
| `REGENOLD_STAGE2_PRIOR_ANSWER_FLOOR` | **`1`** | R420 — the "never ship a thinner answer than the one we already gave" floor on the truncation guard's LAST rung. Before regressing to the deterministic Stage-1 draft, the guard compares against the answer this conversation already holds (`previous_answer` on the flattened history) and, if that answer is complete, ≥400 chars and ≥1.2× the draft, ships IT (`stage2_served_by` = **`prior_turn`**, `stage2_used=True`) instead. The pushback turn re-asks the same question, so the previous answer is a valid answer to it. **MEASURED** (`docs/measurements/r419/CHECKPOINT.md` §4): on the R419 live hard board 4 of 110 rows fell to the deterministic leg because the wrapper returned degenerate one-token completions and the Bedrock leg was dead (`api_key_invalid_403`); re-judging those rows' TURN-1 answers with the published instrument gives **12/12 criteria against 4/12 for the drafts** (`rg_036` 2/3 vs 0/3, `rg_037` 6/6 vs 0/6, `rg_085` and `rg_092` level → the floor correctly does not fire), and restores the two gold heads (`Article 42`, `Annex VIII`). Projected on the same board: `ans_loose` 94.15 → **96.28** (+2.13 pp), `ans_strict` 90.91 → **91.82** (+0.91 pp). `=0` (deny-list) restores the bare deterministic fallback. The `prior_turn` serve is a DEGRADATION: it overrides an earlier `primary` marking, sets `stage2_call_failed`, and the route refuses to cache it (R417 policy). Registered in `_engine_cache_key` |
| `REGENOLD_STAGE2_PRIOR_ANSWER_FLOOR_RATIO` | `1.2` | R420 — how much longer the previous answer must be than the deterministic draft before the floor fires. A malformed value falls back to 1.2 rather than disabling the floor. Registered in `_engine_cache_key` |
| `REGENOLD_STAGE2_DEGENERATE_RETRY` | **`1`** | R417 — retry the primary leg ONCE on a degenerate completion before paying the Bedrock downgrade. The Claude-Max wrapper intermittently relays an interim/empty Claude-CLI assistant message as an HTTP-200 completion (measured live on the graded path: `completion_tokens=1`, a 1-2 char body, `finish_reason=stop`), which the structural guard read as a model truncation — so every blip downgraded the answer to Bedrock. Degenerate = empty/whitespace, <= 2 tokens, or <= 12 chars from <= 6 tokens; a usable Stage-2 completion is 300-1500 chars, so the branch cannot reject real content. The retry re-issues the IDENTICAL request and deliberately does NOT record a second `record_attempt(STAGE2_PRIMARY)` — it is internal to the one attempt, so `attempts == ok + failed` (what `/healthz/llm` reconciles) still holds. If the second call is degenerate too, the failure is named (`graph_rag.wrapper_degenerate_completion_persisted`) and the Bedrock leg takes over, mirroring the R91/R102 guard shape. `=0` restores the pre-R417 single attempt. Registered in `_engine_cache_key` (ON ships tunnel provenance, OFF ships Qwen provenance — different models, different prose, one cache) |
| `REGENOLD_STAGE2_DEGENERATE_RETRY` ↑ companion | — | R417 — `graph_stats["stage2_served_by"]` now names WHICH leg served the shipped polish (`""` = Stage-2 never attempted, `"primary"` = tunnel, `"fallback"` = Bedrock, `"deterministic"` = the wrapper was attempted and the deterministic Stage-1 answer shipped). The route refuses to cache anything but `""`/`"primary"`: a *successful* Bedrock fallback left `stage2_call_failed` False, so the R28 guard could not see it and the degraded answer was CACHED and replayed in 0.1-0.2 s for the worker's lifetime (measured on `rg_010`: one fallback generation read as three separate "observations" long after the wrapper recovered). Also names the truncation-repair's deterministic ship, the second degraded exit that flag never covered |
| `REGENOLD_STAGE2_TAIL_REPAIR_MODE` | **`splice`** | R413 — HOW the truncation guard completes a cut final sentence. BOTH modes now use the transport-proof `GAP:`/`CONT:` join marker (see the R357 bullet above), which is the unconditional part of this round. `sentence` is the reordered rungs — ECHO (accepted only byte-identical to the cut sentence, so it cannot paraphrase a provision away) → RECONSTRUCT the whole final sentence, accepted only when it is exactly ONE sentence, opens with the cut sentence's own opening words, keeps its substance (content-word recall ≥ 0.8) and does not weld a new clause onto a closed one (`_welds_new_clause`) → the tail rung. **Default stays `splice` because the rung-order change has no valid judge leg yet**: the R413 gate's part 3 came back VOID (wrapper OAuth expired mid-run; the fresh scorecard reads `ans_loose` 3.76 % and `regulatory_tone` 2.5 % against 75.9/92.5 for the recorded identity), while its REFERENCE axes — computed deterministically — were flat (`ref_loose` 90.54 in both arms, `ref_strict` 72.52 vs 69.82, `ref_conc` 53.92 vs 53.33 on the *previous* prompt). What IS proven for the new rungs: part 1 is 413/413 recorded complete answers byte-identical with 0 provider calls, and both live probes on the primary leg show the glued word gone and the hedge replaced by the operative provision. Flip when `login.bat` has re-seeded the wrapper and the 8-axis gate carries both arms. Deny-list: any unrecognised value keeps `splice`, so a typo cannot silently change the wire. Registered in `_engine_cache_key` |
| `REGENOLD_STAGE2_FULL_SYSTEM` | **`0`** | R383/R411 — deliver the 53 kB `ANSWER_GENERATE_SYSTEM` on the primary wrapper's system slot instead of the R342 62-char persona. R383 measured 0.199x answer length and 2.38x faster; **R411 ran the paired gate and it SPLITS BY MODALITY**: EASY n=12 is a clean win (resp_speed +13.03 pp, `gold_drop_hd` 1→1, ref_strict +1.85 pp, 12/12 rows faster), but HARD n=37 — the GRADED modality — is a `ref_loose` **−10.81 pp** loss with `gold_drop_hd` **12 → 18 (+6)**, i.e. a hard-rule-#8 FAIL. Mechanism: the full system is what cuts the answer to 0.199x, and hard mode grades the answer to an adversarial PUSHBACK whose contract is to KEEP turn 1's points. **Do not flip the default on the easy-mode number.** The only open form is a single-turn-only gate (`history_turn_count == 1`), which is a new hypothesis needing its own paired run. First instance of a lever whose easy-split probe would have shipped a regression — the probe is not the gate |
| `REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN` | **`1`** | R411/R412 — the full-system lever above, restricted to **single-turn** requests (`history_turn_count <= 1`, the same predicate as `answer_router.is_multi_turn`). The modality split is mechanical, so this isolates the mode where the mechanism that loses refs cannot operate: hard mode grades the answer to an adversarial PUSHBACK whose contract is to keep turn 1's points, and the full system cuts the answer to 0.199x. Baseline predicate is `history_turn_count: int \| None = None` on `_openai_wrapper_complete_for_graph_rag` — `None` means "modality unknown" so the Stage-1 parser and the auxiliary passes are NEVER treated as single-turn. Registered in `_engine_cache_key`. **R412 flipped the default to ON after the paired easy gate ran and PASSED on every axis**, on a wrapper-served sample of n=39 of the 95-row easy split (`docs/measurements/r412/score-singleturn-easy-n39.json`): `ref_loose` 0.8718 → 0.9615 (+8.97 pp), `ref_strict` 0.4333 → 0.5831 (+14.98 pp), `ref_conc` 0.2025 → 0.3481 (+14.56 pp), `kw_recall` +2.56 pp, `gold_dropped_head` **8 → 3** (passes hard rule #8 with room), latency p50 37.40 s → 21.93 s (**−15.47 s**, 37 of 39 rows faster), 0 errors in either arm. Opt out with `=0`. Two earlier readings disagreed and both are explained rather than averaged: the n=12 probe's flat ref axes were a 12-row slice, and a full 95+95 run that appeared to show NO speedup was **VOID** — its log carried **189** `bedrock_auto_fallback` lines (wrapper down ⇒ Bedrock served both arms with the full `system`), while the n=39 gate carries **0**. **Void-ness is read from the run log's fallback count, not inferred from the deltas.** Does NOT extend to `REGENOLD_STAGE2_FULL_SYSTEM`, which still fails on the multi-turn pushback. **R415 proved the scope at the provider seam** (`docs/measurements/r415`): the route derives `history_turn_count` as `max(0, user+assistant messages - 1)`, so a first ask reads **0**, a two-message request reads **1**, a request with ONE completed prior exchange (`user/assistant/user`) reads **2** and is therefore already multi-turn, a direct caller gets the model default **1**, the official hard final reads **9** and the pushback 9/10. (R418 corrected this row: it previously said one prior exchange reads **1**, which contradicted both the arithmetic and the in-code comment, and made the documented `{0, 1}` differ-set look as if ordinary follow-ups were in scope when neither lever reaches them — four review lenses flagged the same line) — and the arms' GRADED payload is byte-identical on every multi-turn row (61-char persona, sha `3bc63d065b58812b`) while differing on every easy row (59644-char full system). The differ-set is `{0, 1}`, the non-vacuity control passes in the same run, and the hard split therefore cannot move: **hard movement 0 by measurement**, against the unconditional flag's `ref_loose` −10.81 pp / `gold_dropped_head` 12 → 18 on that same 37-row ledger. **R415 then judged all EIGHT official axes** on the criteria-bearing corpus (`docs/measurements/r415/official_lever_gate.py`; reconstructed official gold, wrapper judge `claude-sonnet-5`, temp 0.1, grouped, 3 repeats; 26 paired rows the lever actually reaches, both arms tunnel-served, no fallback row in the pair) — the axes the probe-corpus gate structurally could not read, because 0 of the 95 probe questions appear in `official_gold_n110.jsonl`: `ans_conc` **+19.2 pp**, `ref_conc` **+11.2 pp**, `resp_speed` **+3.8 pp**, `ans_loose` **−2.2 pp**, `ans_strict` **−7.7 pp**, ref loose/strict and `regulatory_tone` flat, **OVERALL 64.9 → 71.0 (+6.1 pp)**. The correctness cost is exactly **two rows, one criterion each**, and both are real omissions from the 41 % shorter answer rather than judge variance: `rg_010` drops the *aim* of Art. 14 oversight, `rg_045` narrows "without undue delay" to the informing duties and leaves the suspension unqualified. Reach-weighted by the sweep's 26-of-51 reachable share the lever moves the board geomean by ×1.047 (≈ +3.4 pp at a board value of 72), so **the reach ratio, not the lever, is what bounds board movement**. |
| `REGENOLD_KG_POINT_TEXT` | **`1`** | R409 built it, **R416 flipped it ON** — point text in the Stage-2 KG sub-point block (R408 hop fix + R409 ref-order budget sharing). `=0` (deny-list) runs the exact pre-R408 query, whose inner `MATCH (pt)-[:HAS_SUBPOINT]->(sp)` requires a SubPoint and so returns **0** units for the bare Points that carry most operative limbs (live graph: 421 Points / 37 SubPoints; measure: `docs/measurements/r416/kg_point_text_reach.py`, block changes on **23/26** paired rows, units 26 → 384, text 5,201 → 81,391 chars). Flipped on a paired official-corpus read (`docs/measurements/r415/official-lever-paired-kgpt.json`, 25 paired rows, both arms tunnel-served, wrapper judge 3 repeats): `ans_strict` 88.0 → **96.0** (+8.0 pp), `ans_loose` +2.3 pp, `ref_loose`/`ref_strict` **unchanged at 100.0 / 70.8** (no gold loss — hard rule #8), `resp_speed` +0.9 pp, `ans_conc` −3.3 pp from answers lengthening 1,425 → 1,543 chars, **OVERALL 70.7 → 71.3**. The gain has a named mechanism, not a swing: the only two rows that changed are `rg_010` (4/5 → 5/5, Art. 14's *aim* clause) and `rg_045` (3/4 → 4/4, the scope of *without undue delay*), the two rows the R415 system-prompt compression had broken, and the legacy query returns **0** units for `rg_010`.  **R416 HARD-SPLIT GATE: the unconditional default was FALSIFIED and the lever is now MODALITY-RESTRICTED.** The residual above was gated (paired, 32 tunnel-served rows after the symmetric fallback exclusion, floor 30, both arms primary-served; wrapper judge 3 repeats) and the hard split says the opposite of the easy board: `ref_loose` 80.21 → 75.52, `ref_strict` 43.18 → 40.24, `ref_conc` 22.19 → 19.85, `gold_dropped_head` **12 → 14** — a hard-rule-#8 failure on turn-1 expected heads (`Article 5` on `mt_v4:001`, `Article 51` on `mt_v2:008`, `Article 113` on `mt_v2:020`, `Article 24` on `mt_v2:025`; 6 of 32 rows moved, only 3 favourably). So ON now requires a KNOWN conversation depth `<= 1`; an explicit multi-turn count selects the legacy query, **byte-identical to `=0`** and therefore the measured baseline arm above. `history_turn_count=None` (count not threaded — `logic_rag`, direct engine calls) keeps the shipped ON default. `docs/measurements/r416/CHECKPOINT.md` §6.4 |
| `REGENOLD_KG_POINT_TEXT_SINGLE_TURN` | **`1`** | R416 — the modality restriction on `REGENOLD_KG_POINT_TEXT` above. `=0` removes it and restores the pre-R416 unconditional behaviour, which the hard-split gate falsified. Registered in `_engine_cache_key`. The depth is carried by a `ContextVar` (`kg_context.set_render_turn_count`, set once in `_two_stage_generate`), not a parameter, because nine test fakes patch `fetch_subpoint_detail` with a one-argument lambda and a keyword at that seam is swallowed by `render_kg_context`'s `except Exception` |
| `REGENOLD_CLOSED_SET_COMPLETENESS_GUARD` | `0` | R409 — post-generation check that a list question's engaged closed statutory set is fully stated; one bounded repair call via `_stage2_complete`, accepted only if it closes gaps without dropping or adding a named provision. Targets the 22 OMITTED_ENUMERATED_ITEM criteria of the R407 triage. Counters: `completeness_guard_stats()` |
| ↑ **engagement is now QUESTION-side (R410)** | `0` | The gate used the ANSWER's citations (`prefix_closure(answer_paths)`), so naming any member engaged its whole group: `rg_055` cites Article 5(1)(h) and was asked for Article 5(1)(a)-(g); `rg_064` cites 60(4)(e) and was asked for 60(4)(a)-(k). A group is now engaged only when the question names the parent coordinate exactly **or carries a distinctive chapeau bigram** (both words in <= 1 member of the head). Token overlap does NOT work — the false positives score higher than the true positives (16/15 shared stems for rg_055/rg_064 vs 8/7 for rg_046/rg_052). Measured: fires 13 -> 2, FP on a PASSED row **7/71 -> 0/71**, target-criteria coverage **unchanged at 7/22** (rg_046 Article 13(3), rg_052 Article 17(1)). On the hard split it fired on 1/37 (`mt_v2_004`, one of the four gold-drop offenders of the failed gate) and now fires on **0/37** — the harmful fire is gone. Probe: `docs/measurements/r409/closed_set_engagement_probe.py` |
| ↑ **why it still cannot be flipped ON** | `0` | Run over the whole `easyhard_ab` corpus (132 rows) with the **GOLD** answer as the draft, the lever engages on **0** rows: no corpus row asks for the enumeration of a closed statutory set in the rg_046/rg_052 shape. A live A/B there could only measure Stage-2 sampling noise around a no-op — the exact confound that left the R410 gate's effect size unsettled. Do not run another gate on this corpus; gate on a probe split with enumeration-ask rows, or on the official 110-row benchmark |
| ↑ **GATED AND FAILED (R410)** | `0` | Measured on the hard split, live Stage-2, paired n=37 (`docs/measurements/r409/score-r410-closed-set-gate-hard.md`): **hard rule #8 FAIL** — `gold_dropped_head` 15 → 16 (+1; mt_v2_004/007/015/022), `ref_loose` −0.0135, `kw_recall` −0.0450, est. Overall −0.04 pp; the only gain is `ref_conc` +0.0094. **Do not flip without a gold-drop-safe variant.** ⚠ Attribution is limited: the flag is in `_engine_cache_key`, so the arms generated fresh (0/37 answers byte-identical) and the delta mixes the lever with sampling variance; the detector fires on only 4/37 rows and just 1 of the 4 offenders is one of them. A clean effect size needs a same-generation A/B — but the gate verdict itself (drop ZERO) stands |
| `REGENOLD_EXCEPTION_LIMB_GUARD` | `0` | R409 — same repair path, for exception/condition clauses ("unless", "with the exception of", "provided that") of provisions the answer names, on questions that ask about exceptions or conditions (9 criteria) |
| `REGENOLD_VERDICT_LEAD_GUARD` | `0` | R409 — same repair path, for a yes/no question whose answer does not open with Yes or No (6 criteria). **R410 fixed the detector's precision** (`answer_completeness.py`): it required the literal token `Yes`/`No` (so "Not prohibited and not high-risk." counted as no verdict at all) and read the LAST interrogative of a multi-clause question. Measured on the frozen 110-row R407 ledger (`docs/measurements/r409/answer_completeness_offline_validation.py`, all flags ON): fires **11 → 2** rows, false positives on a PASSING row **6/71 → 0/71**, target recall 1/6 → 2/6. Still OFF because n=2 is too small to gate; the two fires are genuine lead-shaped defects (a conditional framing, and a verdict outside the lead) |
| `REGENOLD_PUSHBACK_KEEP_CONTRACT` | `0` | R409 — on a challenge turn, a USER-channel clause listing the previous answer's anchored points to keep, plus a post-check that repairs points dropped without a stated legal reason (7 PUSHBACK_DRIFT criteria) |
| `REGENOLD_GOVERNING_PROVISION_CLAUSE` | `0` | R409 — USER-channel clause for "which provision governs X" questions: state what each numbered paragraph of the governing provision requires (targets the WRONG_OR_MISSING_PROVISION shape) |
| ↑ **NOT gated — the other detectors are still imprecise** | `0` | `exception` fires on 6 of 71 PASSING rows and hits 0/9 target criteria by coordinate; `keep_clause` fires on 107/110 rows, so it carries no signal. (`member` is fixed — see the closed-set row above.) Table: `docs/measurements/r409/answer_completeness_offline_validation.py` |
| **TrustGraph `coordinate_exists` as a wire guard — MEASURED, NOT ADDED** | `REGENOLD_REF_COORD_GUARD=1` | 962 live wire references replayed through the generated oracle (110 R407 `pred_refs` + 110 `turn1_refs` + 37+37 R410 gate arms): **0 non-existent coordinates (0.00%)**. The guard already exists (`_repair_nonexistent_coordinates`, `regenold.py:4078`, default ON) and folds an unreal coordinate back onto its head head-preservingly, so 0 is the POST-guard reading and a second guard would be a no-op that can only lose gold heads (hard rule #8). TrustGraph's remaining value is the SPARQL-queryable A-Box (`trustgraph-integration/`), not a reference guard. See R410 handoff §6.10 |
| `REGENOLD_SCOPE_STOP_RULE` | `0` | R367 scope stop rule on the Stage-2 USER channel: answer the question, then STOP; never append a neighbouring provision/power/mechanism/derogation the question did not raise. Targets BOTH conciseness axes (combined leverage 0.364 pp/pp). **Prompt-side ⇒ NOT reference-neutral** (AGENTS.md invariant #5), so it needs `easyhard_ab`/`gold_dropped_head` AND `ab_judge` before flipping |
| `REGENOLD_PROMPT_V2` | `1` | R377 port (PR #368): selects the four rebuilt V2 USER-channel clauses (coverage incl. `LEGAL VERSION` Omnibus exclusion, reference minimality, sub-paragraph discipline, and the CHALLENGE clause that instructs `<reasoning_scratchpad>`/`<answer>` channels on pushback turns). Shipped default ON on a gate claim with no record — see § R379 for the Bedrock A/B. Lives in `app/data/`, which the R355 AST gate does NOT scan; registered in `_engine_cache_key` by hand |
| `REGENOLD_FIDELITY_TIER_NEGATION` | `1` | R377-B port: the cross-tier fidelity CONTRACT is what the deterministic draft ASSERTS, not what it mentions — a sentence-local denial ("not high-risk") no longer counts as an asserted tier. `=0` restores the anchor-only reading |
| `REGENOLD_PROMPT_V3` | `0` | R380 — ONE compact ANSWER DISCIPLINE block (scope, completeness of what was asked, length, citations, terminology, grounding, Article 5 verdict check) appended LAST on the Stage-2 USER channel; withholds the V1/V2 coverage / critical-rules / minimality / sub-paragraph / terminology clauses, the breadth tail ("state both the prohibited context AND its treatment elsewhere", "rule 12b"), the CROSS-REFERENCED PROVISIONS block and the R367 scope stop rule, and relabels the draft as over-inclusive source material. Prompt-side ⇒ NOT reference-neutral; see § R380 for the measured arms |
| `REGENOLD_REASK_ANCHORLESS` | `1` | R380 — the R305 re-ask focus accepts a "let's try again:" tail without an AI-Act anchor (length + leading-coreference gates still apply). The evaluator's verbatim pushback fired the focus on 100/110 official questions; the 10 misses went through the de-noiser into the 40-turn concatenation. `0` restores R305 |
| `REGENOLD_DENOISER_MAX_TOKENS` | `400` | R380 — completion budget of the multi-turn query rewrite (was a hard 100). The Groq slot runs `openai/gpt-oss-120b`, a reasoning model whose hidden reasoning counts against `max_tokens`, so the rewrite truncated on 5/9 multi-turn calls live and every provider in the chain fell through to concatenation. **R381: still accurate — the model is `openai/gpt-oss-120b` again**, see the row below |
| `REGENOLD_DENOISER_MODEL_GROQ` | `default_groq_model()` = `openai/gpt-oss-120b` | **R381 — a P0 was shipped and reverted here.** `f46adb8` hardcoded `llama-3.3-70b-versatile`, which **does not exist on this Groq account**: `GET /openai/v1/models` returns 14 ids and that is not one of them; a POST returns `404 model_not_found`. So every Stage-0 rewrite 404'd and fell through to the 40-turn concatenation — the exact history bleed R380 had just fixed. The same commit also passed `reasoning_effort="none"` explicitly, which **400s** on gpt-oss (`must be one of low, medium, or high`) and is *unnecessary*: `openai_wrapper_provider.py:555-568` already auto-injects the right value per family (gpt-oss → `low`, qwen → `none`). Measured live: no effort 83 completion tokens / 0.6 s; `low` **30 tokens / 0.2 s**. The valid value is family-specific, so never hardcode one at the call site |
| `REGENOLD_DUAL_PASS_RETRIEVAL` | `0` | R380/`f46adb8` — replaces the Stage-0 LLM rewrite with deterministic dual-pass retrieval: pass 1 parses the live user turn (operative provision), pass 2 the prior USER turns only (context anchors, R91: assistant text never reaches entity extraction or BM25), then an ordered dedup fusion. **Default OFF**, and verified so by execution (unset ⇒ 0 `dual_pass_parse` calls; `=1` ⇒ it fires and the fused entity list differs). Registered in `_engine_cache_key`; single-turn is a strict no-op (10/10 byte-identical). ⚠ **Known P0 while ON:** it pre-empts R380's `REGENOLD_DENOISE_SELF_CONTAINED_SKIP`, which re-opens assistant-turn bleed on the wire and drops gold refs — do not flip it on without re-gating |
| `REGENOLD_REF_GRAIN_DEEPEN` | `1` | **R386/R388 — the reference gap is GRAIN, not precision.** Replaces a bare head with its question-and-answer-relevant paragraph (`Article 13` -> `Article 13.3`). Shipped default ON (R388). The evaluator's own printed answer keys are **~71 % sub-point**; we ship **14.3 %**, and Ref Loose (89.4) is ALREADY level with Ans Loose (89.7) while Ref Strict (68.3) lags Ans Strict (81.2) — a 21-point loose/strict spread that is a grain deficit. **Free by construction, then verified**: `gold_dropped_head` folds onto heads (its own docstring: *"a MORE precise prediction than gold ... does NOT count as a drop here"*), RefConc is a pure COUNT ratio and the count is unchanged, Ref Loose is head-level and the head survives inside the leaf. Gate replay n=129: **gold 37 -> 37 (+0) with every axis byte-identical while 284 references change.** On the R386 minimal-gold set, n=99: **Ref Strict 18.3 -> 36.5 (+18.2 pp)**, RefLoose and RefConc untouched. Coordinate accuracy 77 % (47/61) against 4 rows where gold wanted the bare head; thresholds are a PLATEAU (every `MIN_TOP` 1-6 x `MIN_MARGIN` 1-4 scores 35.5-37.0, none drops a gold head), so the gain is not a fitted parameter. Ordered AFTER parent collapse and BEFORE every pass that can drop, so a dropped ref is never a deepened one. See § R386 |
| `REGENOLD_REF_GRAIN_DEPTH` | `1` | R388 — maximum sub-level depth for grain deepening (1 = paragraph/item level e.g. `Article 13.3`, >1 = sub-points like `13.3.a`). Defaults to `1` as verified by zero-variance replay against the official rubric answer key. Registered in `_engine_cache_key`. |
| `REGENOLD_WHOLE_HEAD_FLOOR` | **`1`** | R442 floor, gated in R447. Raises the Stage-2 ANSWER SHAPE target to the 650-char no-signal floor when the ask names a bare listed head, nothing is engaged, and the ask is not a NARROW verdict ask (yes/no with no open request in any sentence; "What is Annex X about?", rg_105). R442 shipped it ungated, and it also fired on verdict questions ("Does Article 26 require deployers to keep logs?" 375 → 650). Route replay: 0 answer-shape changes on the official 110; 3 probe rows, all yes/no. Deny-list; `=0` restores R439's proportional target. Registered in `_engine_cache_key` |
| `REGENOLD_CURATED_KEEP_DECLARED_LEAVES` | **`1`** | R447. For a curated authoritative intercept, R87-C does not re-emit a head whose declared leaves have no dominating member (`_undominated_leaf_heads`). Otherwise, at a compound-role budget of 12, R287 folded those leaves into the manufactured head and the deepener kept one: the Art. 50 information route cited `Article 50.4` alone, and the role route never cited `Article 3.4`. A bare copy of such a head added by another pass (`expand_citations` on scenario shapes) is dropped before R287 while its leaves are listed. Dominated clusters (`Annex III.8` over `8.a`/`8.b`) still fold. A blanket skip cost rg_012 Ref. Conciseness 1.00 → 0.33. Two-arm replay (`docs/measurements/r447/curated_leaves_replay.py`) and a 1,077-variant sweep: every change a win or neutral, 0 on the official 110. Deny-list; registered in `_engine_cache_key` |
| `REGENOLD_WIRE_REF_CAP` | `0` (unlimited) | R381 — terminal cap on the emitted reference list, the LAST reference pass. Built to attack the highest-leverage axis (RefConc is `min(1, \|expected\|/\|provided\|)`, a pure COUNT ratio) and **GATED, THEN REJECTED**. Zero-variance simulation over a full live capture of the gold-bearing probe corpus, n=129: cap 5 → gold 37→37 (+0.03 pp), cap 4 → 37→37 (+0.33 pp), **cap 3 → 37→41 FAILS**, cap 2 → 65 FAILS, cap 1 → 113 FAILS. **Every value worth having fails hard rule #8; every value that passes is worth nothing.** ⚠ The verdict REVERSED as n grew — cap=3 read "pass" at n=17/30/34 and fails by 4 at n=129, monotonically worse. Zero-variance removes GENERATION variance, not SAMPLING variance. Kept in the tree at `0`, cache-keyed and tested, so the measurement can be re-run if the evaluator's real expected sets ever land. Malformed value fails OPEN. See § R381 and `docs/reviews/r381-…` |
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
**R381 — collapse is now default ON**, so that interaction does ship; the guard
being ADD-only-of-an-absent-base is what makes the ordering safe.

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

⚠ **CORRECTED R381 — it was gated, and it PASSED. Flipped to default ON.**
The paragraph here used to read *"Gate before flipping it. It DROPS references —
the R142.1 failure mode … Ship only behind an `evals.harness.easyhard_ab` win."*
That gate was never runnable on this lever: the collapse is a strict no-op
offline (paragraph above) and it fires on ~20% of LIVE rows, so `easyhard_ab`'s
probe corpus reads +0.0000 for the same reason the R329 rerank placements did.

**What was run instead is strictly stronger — a live paired A/B where the noise
is eliminated rather than averaged.** n=20 official questions over the
cloudflared wrapper, arms interleaved per row, 40/40 calls wrapper-served, 0
Bedrock fallback. Thirteen rows moved on live Stage-2 generation variance and
are discarded. **Four rows have a byte-identical answer in both arms**, so the
reference list is the only thing that can have moved:

| row | refs | dropped | survives |
| :--- | ---: | :--- | :--- |
| `rg_013` | 5 → 4 | `Article 53` | `Article 53.2` |
| `rg_025` | 3 → 2 | `Article 25` | `Article 25.1` |
| `rg_029` | 4 → 2 | `Article 6`, `Annex III` | `Article 6.2`, `Annex III.5.d` |
| `rg_041` | 4 → 2 | `Article 11`, `Annex IV` | `Article 11.1`, `Annex IV.2` |

All **6 drops are bare parents whose own sub-point is still on the wire** — no
provision leaves the citation set — and the **HEAD SET is unchanged on all four
rows**. `gold_dropped_head` folds both sides onto heads
(`evals/bench/metrics.py:572-574`), so **hard rule #8 delta is +0: measured, not
argued.** Lever-only Ref. Conciseness **51.3 → 56.3 (+5.0 pp) ⇒ +0.90 pp
Overall**.

**And it is not the R142.1 family at all**, which is the reasoning error that
kept it off for three rounds. R142.1 is a POSITIONAL clamp that drops a ref the
list does not otherwise carry. This drops a ref the list carries *twice*. On the
official rubric: Ref Loose is scored *"at the level of Article and Annex
numbers"* so the head survives inside the leaf; Ref Strict *"includes subpoints"*
so the leaf is strictly better than the parent it replaces; and Ref Conciseness
is `min(1, |expected|/|provided|)` (§ R381), a pure count ratio — so removing a
redundant duplicate is free score on all three. The R274 trade pinned in
`test_r325_parent_collapse.py::TestKnownTradeIsPinned` is that same shape, and
that test already asserts the head grain still carries `Article 6`.

**The generalisable lesson:** when a lever is a *deterministic transform* and the
sanctioned harness cannot reach it, the answer is not "ship it ungated" and not
"leave it off forever" — it is to find the rows where the confound is absent.
Here that was rows whose answer is byte-identical across arms; the R317
zero-variance simulator is the same idea one layer down.
