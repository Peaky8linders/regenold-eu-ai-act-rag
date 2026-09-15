# R416 — findings validation, the KG point-text lever, and two instrument fixes

**Date:** 2026-09-13 **Branch:** `fix/r409-r408-audit`
**Input:** the pasted "SOTA proposal vs code gap" analysis (7 domains) plus a parallel
review pass over the same claims.
**Disposition of every finding:** `docs/reviews/r416-findings-validation.md`.

---

## 1. What shipped

**`REGENOLD_KG_POINT_TEXT` is DEFAULT ON for single-turn asks and scoped OFF on
multi-turn ones** (§6.4). The gap report's finding 1.2 was
right and is the only finding that turned out to be an ungated *lever* rather than a
documented decision: production was serving `_SUBPOINT_CYPHER_LEGACY`, whose inner
`MATCH (pt:Point)-[:HAS_SUBPOINT]->(sp:SubPoint)` requires a SubPoint, while the live
graph has **421 Points and 37 SubPoints**. Stage-2 was therefore given no statutory
point text for the bare Points that carry most operative limbs — the generation-
omission class F1 named, one layer down.

### Reach first, deterministically, before spending a call

`docs/measurements/r416/kg_point_text_reach.py` (live Aura, no model calls) calls the
production `fetch_subpoint_detail` twice per row over R415's 26 paired rows:

| | OFF | ON |
| :--- | ---: | ---: |
| rows whose block changes | — | **23 / 26** |
| units | 26 | **384** |
| text chars | 5,201 | **81,391** |

It then asks the question that decides whether a gate is worth running: the R409 triage
recorded omitted enumerated coordinates on 12 rows. On `rg_046` the ON arm supplies
**`Article 13.3.a`, `.c`, `.d`** — the limbs the graded answer had missed. Two of that
row's five gaps (`13.3.e`, `.f`) are absent from both arms, so the lever is a partial
fix on that row and is recorded as one.

### The paired read

25 paired rows (comparable on both arms), both arms tunnel-served, wrapper judge
`claude-sonnet-5` temp 0.1 grouped r=3, baseline = the **shipped** configuration so the
arms differ by exactly one flag
(`official-lever-paired-kgpt.json`, `score-r415-official-lever-{a,b}-matched-kgpt-easy.json`):

| axis | OFF | ON | Δ pp |
| :--- | ---: | ---: | ---: |
| ans_correctness_loose | 96.6 | 98.9 | **+2.3** |
| ans_correctness_strict | 88.0 | 96.0 | **+8.0** |
| ans_conciseness | 47.8 | 44.5 | −3.3 |
| ref_correctness_loose | 100.0 | 100.0 | 0.0 |
| ref_correctness_strict | 70.8 | 70.8 | 0.0 |
| ref_conciseness | 51.6 | 52.2 | +0.6 |
| regulatory_tone | 60.0 | 60.0 | 0.0 |
| resp_speed | 70.4 | 71.3 | +0.9 |
| **OVERALL** | 70.7 | **71.3** | **+0.6** |

`ref_loose` flat at 100.0 clears hard rule #8 (the precondition the flag's own docstring
had set), and the correctness gain is mechanistically named rather than a swing: **the
only two rows that changed are `rg_010` (4/5 → 5/5, the Art. 14 *aim* clause) and
`rg_045` (3/4 → 4/4, the scope of *without undue delay*)** — exactly the two rows the
R415 system-prompt compression had broken — and the legacy query returns **0** units for
`rg_010`, so the missing clause is explained by the missing text. Reach probe and gate
were run independently and agree on the same row.

Cost: answers lengthen 1,425 → 1,543 chars, which is the −3.3 pp of conciseness. Net
mean latency improves (29.6 → 28.7 s). `=0` reverts.

## 2. Two instrument defects found and fixed

Both were in `docs/measurements/r415/official_lever_gate.py`, and both would have
produced a wrong *conclusion* rather than a wrong number.

1. **The fallback doctrine was applied to one arm and withheld from the other.** A row
   served by the Bedrock leg is structurally incomparable (that leg always receives the
   full `system`), so R415 dropped such rows from the pair. R416's new arm had **2**
   fallback rows, and the void check — which read the unfiltered files — withheld the
   entire table for them. Both arms now apply the same drop, with a refusal when the
   drop exceeds half an arm (a residue of a broken transport is not a matched A/B).
2. **The one-flag invariant.** The first table on this data read **+6.1 pp overall** and
   was thrown away: arm A was the R415 arm-A run (`..._SINGLE_TURN=0`) while a new arm-B
   run picks up that lever's shipped default (`=1`), so the arms differed by **two**
   flags and the delta was their blend. The gate now takes `--baseline` and prints both
   run names above the table. The honest read of the same data is **+0.6 pp overall and
   +8.0 pp on Ans Strict**. Both the discarded blend and the real reading are on disk.

The gate also gained `--flag` / `--arm-values` / `--tag` / `--reach-from`, so any lever
can be paired on this corpus. Because the reach set belongs to the *route*, a new lever
reuses R415's reach list and pays for **one** arm of calls, and the untouched arm's
verdicts are a judge-cache hit — this round cost one arm, not two.

## 3. Corrections to prior evidence (so they are not used again)

* **The easy board's `ans_strict` +8.0 pp is a single-draw pair, not a gain.**
  Re-scored in R419 (`docs/measurements/r418/kg_lever_ans_strict_repro.py`). The
  entire answer-correctness movement of this lever is **two criteria out of 87**
  across the 25 paired rows — `rg_010`'s Art. 14 *aim* limb (which is the +2.3 pp
  of `ans_loose` as well, 2/87) and `rg_045`'s *without undue delay* limb — and
  neither survives resampling: `rg_045`'s credit appears in only 2 of the judge's
  3 own repetitions, and **10 fresh generations per arm** credit `rg_010`'s limb
  at the same rate on both arms (KG=0 6/10, KG=1 5/10; atomic draws 18/30 vs
  15/30, Fisher p=1.00). On the surviving rows Ans Strict is **95.65 vs 95.65
  (+0.0 pp)**. The `-3.3 pp` conciseness "cost" in §1 is likewise not supported:
  the ON arm is longer on only 14 of 25 rows (sign-test p=0.69). **Read every
  *scored* number in §1 as one draw per row per arm; the reach and mechanism
  evidence (§6.1, and the deterministic reach in §1) is unaffected, as is §6.4's
  hard-split scope, which was measured independently.**

* **Roadmap row 4 (sub-point grain) is CLOSED.** Its premise — "keys ~71 % sub-point vs
  our 14.3 %" — is stale. The recount on the frozen ledger (inputs pinned by SHA-256;
  dot-in-coordinate test on both sides; no head folding, which would erase the property)
  gives **85.81 % emitted vs 84.44 % expected**. There is no 5× deficit for
  `COORD_MAP_PROMPT` to close.
* **The F7 member-recall evidence was void.** `member_recall_probe.py` read
  `answer`/`final_answer`; the checkpoint stores `pred_answer`. It diagnosed empty
  strings for all 110 rows and printed a plausible histogram. Repaired and
  input-validated: 7 not-list / 3 engaged / 1 question-not-engaged / 1 answer-not-naming;
  engaged rows `rg_043`, `rg_046`, `rg_052`. The independent precision replay stands:
  **0/71** passing rows fired, 2/12 target rows, 7/22 target criteria.
* **CLARA is not dead code** and **the cache-key AST gate does cover `app/llm/`** — both
  `AGENTS.md` claims corrected, both pinned by
  `tests/test_r416_route_architecture.py`.
* **Cohere context reranking is default ON** (R400); the report's "default OFF" is stale.

## 4. Residuals

* **The hard split is unmeasured for this lever**, and unlike the R415 lever it is not
  modality-restricted. Its direction is opposite to the class that broke hard mode
  (answers lengthened slightly, no reference axis moved, `gold_dropped_head` untouched) —
  but that is reasoning, not measurement. This is the next gate.
* `REGENOLD_GRAPH_FUSE_SLACK` is confirmed inert at its default (660 candidates
  available, 4 added over 132 rows) but the question that would settle the family —
  whether those candidates contain gold heads BM25 misses — is still unanswered.
* The content-preservation contract (row 3) is better specified but unwritten: R415
  named the operand (a qualifier's scope narrowing), this round shows the KG lever
  recovers that exact row, but no deterministic guard exists that catches it without
  firing on passing rows.
* Row 4 is closed on the frozen ledger, not on live output.

## 5. Live confirmation (deploy `84df3d3f8c24`)

`docs/measurements/r415/live_prod_check.py` re-asks production for the two rows, and
reports the clauses rather than asserting them (the flip traded a small conciseness cost
for them, so a missing clause is a residual to re-verify, not a test failure):

| row | clause | deploy `f658a49` (pre-flip) | deploy `84df3d3f8c24` (post-flip) |
| :--- | :--- | :--- | :--- |
| `rg_010` | Art. 14 *aim* — "preventing or minimising risks to health, safety or fundamental rights" | **absent** | **present** |
| `rg_045` | *without undue delay* adjacent to the suspension | present | present |

Production has **no `railway.toml` / `.env` override** for `REGENOLD_KG_POINT_TEXT`
(checked), so the code default is what governs live and no deploy-env change was needed.

**Do not read a single live ask as a rate.** Two consecutive live asks of the same
`rg_010` question returned 1,230 and 350 chars — the short one omitted the aim clause —
which is the live sampling spread, and exactly why the 25-row 3-repeat judge, not a spot
check, is the measurement above. The live check is a deploy smoke test that the flip is
in effect; it is not evidence for the +8.0 pp.

## 6. The hard split, and the instrument bug that had to be fixed first

§4 named one residual: this lever's hard-split movement is **unknown**, not zero — it
is a grounding-text change, so unlike the R415 system-slot lever it is not
modality-restricted. This section is that measurement.

### 6.1 Reach, before spending a call (deterministic, live Aura)

`kg_point_text_hard_reach.py` drives the real route with the provider stubbed to a
recorder and diffs the graded Stage-2 **user** payload between the arms:

| sample | rows | graded | payload changed | KG block chars OFF → ON |
| :--- | ---: | ---: | ---: | ---: |
| `paper_mt_v4` head | 4 | 4 | **4** | 4,344 → 20,781 |
| `mt_v2` tail | 5 | 5 | **5** | 1,204 → 28,017 |

9/9 across both hard source families, so a paired hard gate measures the lever rather
than noise. (Total user-payload length moves both ways — the unit budget is shared, so a
larger point-text block evicts other context on some rows.)

### 6.2 `ArmProbe` stripped the Cloudflare Access service token — 74/74 calls fell back

The first two hard runs were VOID: `primary_attempts=37, primary_ok=0, fallback_ok=37`
on **both** arms, while a direct call in the same environment, minutes apart, was served
**10/10** by the primary.

Mechanism: `_OpenAIWrapperProvider` resolves its CF Access service-token headers **once,
at construction**, and caches them. `app.config` is what puts `.env` into `os.environ`,
and it does so lazily on first import — which, before this fix, happened **after**
`gate_validity._PayloadRecorder.install()` had already constructed the provider
singletons. They then carried no `CF-Access-Client-*` header and no `OPENAI_API_BASE`,
so Cloudflare Access refused every primary call with a 401 and the run was served by
Bedrock. Confirmed by the absence of `cloudflare_access_service_token_active` anywhere in
the gate log, against its presence in a direct run.

This is the R412 near-miss class — a VOID run that reads as a plausible null — except
**self-inflicted by the module that exists to detect it**. Fixed by importing
`app.config` in `install()` before any provider is touched (it honours
`REGENOLD_SKIP_DOTENV` and skips under pytest, so offline/test arms are unchanged).

Verified by the same 2-row arm under the same `ArmProbe`: `primary_ok=0` → **`primary_ok=2,
fallback_ok=0`**.

### 6.3 Two more gate defects, fixed so the finding can be reported at all

* **No per-row transport provenance.** The ckpt recorded only an arm-level total, so a
  single fallback row voided a complete 37+37 run with no way to say *which* rows the
  other leg carried. Rows now carry `stage2_primary_ok`, `stage2_fallback_ok`,
  `stage2_used`, `stage2_fell_back`.
* **One fallback row voided everything.** `assess` voids when the fallback leg carried
  any row — right for a system-slot lever (Bedrock always gets the full system), wasteful
  for every other kind, where a grounding/user-payload lever reaches **both** legs.
  `_exclude_fallback_rows` now drops the SAME ids from both arms (symmetry is the point:
  R415's first draft dropped one side and voided on the other), the drop is printed, and
  the run is still refused when survivors fall below `_MIN_GATE_N`.

`tests/test_r416_gate_provenance_and_dotenv.py` pins all four (8 tests), including the
ordering invariant that a provider is never constructed before `app.config` loads.

### 6.4 The paired hard read — THE REVERT, TAKEN AS SCOPE NOT AS LOSS

`r416d-kgpt-hard`: 37+37 rows, clean one-flag arms (`REGENOLD_KG_POINT_TEXT=0` vs `=1`),
both arms primary-served on 35/32 rows. The gate process itself voided (it was launched
before §6.3's exclusion existed), so the read is the **re-score** from the same on-disk
rows by `score_hard_split.py`, which calls the gate's own `_exclude_fallback_rows`,
`_aggregate`, `_paired` and `_gold_gate_verdict` — no second implementation.
Five ids dropped symmetrically (`mt_v4_009`, `mt_v2_004`, `mt_v2_009`, `mt_v2_014`,
`mt_v2_016`); **32 paired rows survive**, floor 30.

| axis | OFF | ON | delta |
| :--- | ---: | ---: | ---: |
| ref_correctness_loose | 80.21 | 75.52 | **-4.69** |
| ref_correctness_strict | 43.18 | 40.24 | -2.95 |
| ref_conciseness | 22.19 | 19.85 | -2.34 |
| regulatory_tone | 100.0 | 100.0 | 0.0 |
| keyword_recall | 81.25 | 79.69 | -1.56 |
| **gold_dropped_head** | **12** | **14** | **+2** |

**HARD RULE #8 FAILS.** Four rows newly drop a turn-1 expected head the baseline kept:
`Article 5` (mt_v4:001), `Article 51` (mt_v2:008), `Article 113` (mt_v2:020),
`Article 24` (mt_v2:025). Six of 32 rows moved; three moves were favourable, so this is
not a swing that averages out.

**The revert, taken as modality scope rather than as global loss.** The R416 easy board
measured the same lever UP (+8.0 `ans_strict`, +0.6 overall, `ref_loose` flat at 100.0 on
25 paired rows). Both readings are real and the predicate is what separates them: the easy
board is single-turn, the loss is on multi-turn pushbacks. So the default is unchanged for
single-turn asks and falls back to `_SUBPOINT_CYPHER_LEGACY` when the conversation depth
is known to be >= 2 — byte-identical to `REGENOLD_KG_POINT_TEXT=0`, i.e. the measured
baseline arm above. `REGENOLD_KG_POINT_TEXT_SINGLE_TURN=0` restores the falsified
unconditional behaviour; it is registered in `_engine_cache_key`.

The depth rides a `ContextVar` (`kg_context.set_render_turn_count`), set once in
`_two_stage_generate` — the single ancestor of both Stage-2 entry points — and reset in a
`finally`. Not a parameter: **nine** test fakes patch `fetch_subpoint_detail` with a
one-argument lambda, and a keyword at that seam is swallowed by `render_kg_context`'s
`except Exception`, silently emptying the block (that swallow now logs).

### 6.5 Post-deploy live confirmation of the SCOPE (`04aa6c9ebf59`)

`docs/measurements/r416/live_prod_check.py` — the scope is a predicate, so BOTH halves
were asked on the real transport (production Stage-2), not just the arm that improved:

| case | turns | chars | wire refs | names Article 14 |
| :--- | ---: | ---: | :--- | :--- |
| single-turn | 1 | 417 | `['Article 14.4']` | yes |
| multi-turn pushback | 11 | 2,095 | `['Article 14.4', 'Annex III.1.a']` | yes |

Asserted and passed: healthy deploy, non-empty answers, wire references present, the
operative article named on BOTH paths. The hard path is the point — the legacy query
does not empty the block or break the answer when it is selected.

#### 6.5a The aim-clause gap, resolved: a TRANSPORT artifact, not a route — and it sticks

The §6.5 single-turn sample (417 chars) omitted Art. 14's *aim* clause, which the R416 easy
gate had credited to `rg_010` (4/5 -> 5/5). `aim_clause_probe.py` resolved it, and the
first reading recorded here ("a route difference") was **wrong**:

1. **The clause is not systematically lost.** A cache-busted live ask ("Which article of
the EU AI Act governs human oversight?") took 21.7 s and returned **783 chars that DO
state it** — "the oversight must aim to prevent or minimise risks to health, safety or
fundamental rights" — with `stage2_model=claude-opus-5 complex=False`,
`answer_route=synthesis:synthesis_default`, intent `article_lookup`, and **no** fallback
note. Two other live single-turn shapes state it too ("What does Article 14 … require?"
2,109 chars; "Must … and to what end?" 1,618).
2. **Every sample WITHOUT the clause coincides with a non-wrapper generation**, and two
say so in the trace: local KG=1 — `openai_wrapper_truncated_structural …
(model=claude-opus-5, completion_tokens=1)` -> `bedrock_auto_fallback` -> `tail repair
failed — shipping deterministic Stage-1 answer` (1,037 chars, no aim); local KG=0 —
`stage2_model=qwen.qwen3-32b-v1:0 provider=bedrock` + `bedrock_auto_fallback_success`
(815 chars, no aim). Every wrapper-served sample states it.
3. **The three production "aim-less" observations were not independent.** Repeated asks of
the identical question returned in **0.1-0.2 s** (cache hits) while a novel question took
**38.4 s**. So `rg_010`'s short answer was one non-wrapper generation, cached per worker
and replayed; 456/493/501 were not three samples.

**Why it sticks — the R28/R78 cache-poisoning class, uncovered for a SUCCESSFUL fallback.**
`stage2_call_failed` is set only when BOTH legs fail (`enhanced is None`), so a successful
Bedrock fallback leaves it False; `_cacheable` then passes (`stage2_call_failed` False,
`confidence` 0.7 >= `_MIN_CACHEABLE_CONFIDENCE` 0.3, `nodes_traversed > 0`) and the
**fallback answer is `put` into the process-local `_ENGINE_CACHE`**. `graph_stats` carries
`stage2_call_failed` and `stage2_landed` but **no "which leg served this"** marker, so the
route cannot tell a wrapper answer from a fallback one when deciding to cache. Measured
consequence: production replayed a fallback-served `rg_010` answer at 0.1 s across separate
probes and across both workers.

**Consequence for the lever's narrative.** The R415 pair (arm A 1,125 chars no-aim, arm B
1,350 aim) is a 1-vs-1 comparison on a **`article_lookup`** question, whose answer is brief
by construction, so whether the model volunteers 14(2)'s purpose clause is sampling
variance at that brevity. Fresh local samples show the clause on **both** arms (KG=1 1,387
aim=True; KG=0 1,201 aim=True). `rg_010` therefore **cannot** be cited as the lever's
mechanism; the paired judged board delta is unaffected (it is whatever the judge scored),
but the named-mechanism claim is retracted. The wire reference on the row is
`ref_grain_deepen Article 14->Article 14.4` — post-processing, not generation.

### 6.6 The re-score driver's own bug, found and fixed

First run of `score_hard_split.py` **refused** a passing sample: it floor-checked
`survivors.values()` (`{'easy': 0, 'hard': 32}`) instead of the splits the corpus carried,
so a hard-only run's empty `easy` key read as a floor breach. `easyhard_ab` has always
used `expected_splits`; the driver now does too (`--splits`, default `hard`).

## 7. Artifacts

| file | what |
| :--- | :--- |
| `kg_point_text_reach.py` / `kg-point-text-reach.json` | deterministic reach (live Aura) |
| `validate_frozen_findings.py` / `frozen-summary.json` | the frozen recount (SHA-pinned inputs) |
| `member-recall.json` | repaired per-row member-recall evidence |
| `../r415/official_lever_gate.py` | the reusable paired gate (`--flag`, `--baseline`) |
| `../r415/official-lever-paired-kgpt.json` | this round's paired reading |
| `../r415/official-lever-b-matched-kgpt.ckpt.jsonl` | the graded answers behind it |
| `../r415/judge-cache-r415-wrapper.jsonl` | the judge verdicts (shared cache) |
| `../../reviews/r416-findings-validation.md` | disposition of all 12 findings |
| `kg_point_text_hard_reach.py` / `kg-point-text-hard-reach{,-tail}.json` | §6.1 reach |
| `score_hard_split.py` | §6.4 re-score (symmetric fallback exclusion) |
| `hard-split-r416d-kgpt-hard.json` | §6.4 the verbatim hard-split read |
| `anchor_precision_measure.py` / `anchor-precision.json` | the unbacked anchor-precision claim, measured |
| `tests/test_r416_gate_provenance_and_dotenv.py` | pins §6.2 and §6.3 |
| `tests/test_r408_kg_context_point_traversal.py` | pins §6.4's modality scope (4 new tests) |
| `tests/test_r416_audit_remediations.py` | pins the audit remediations |
| `live_prod_check.py` | §6.5 post-deploy live check of both modalities |
| `aim_clause_probe.py` | §6.5a the aim-clause resolution (transport, not route) |
