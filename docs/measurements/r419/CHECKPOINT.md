# R419 — the live HARD re-eval (110 rows, primary leg) + the prior-answer floor

**Branch** `fix/r409-r408-audit` · **base commit** `feafe2f` (PR #431 → merged `7ef9df05f3d9`,
deployed `7ef9df05f3d9`, verified on `/healthz.commit`).

---

## 1. The run

```
.venv/Scripts/python.exe -m evals.regenold.run_official_batch \
    --label r419-hard --mode hard --timeout 240
```

* per-row ckpt `evals/bench/results/official-r419-hard-hard.ckpt.jsonl` — **110/110 rows**
* in-process engine on merged `main`, Stage-2 primary = the Claude-Max wrapper **via the
  cloudflared tunnel**; `stage2_served_by` on the wire per row
* non-200 responses **0** (the R418 echo-trim fix holds; the R418 422 cascade is gone)
* leg mix: `primary` **81** · `deterministic` **4** · `unrecorded` 25 (the curated
  deterministic-by-design subset — its id pattern is byte-identical to R390/R407)
* refusals **0** · gold heads dropped **4** rows · pushback changed the reference set on **46**
  rows (mean head Jaccard 0.8298)

## 2. The board (all eight axes, n=110)

Judged with the published instrument, `openrouter:qwen/qwen3-235b-a22b-2507:t=0.1:grouped:r=3`,
cache `docs/measurements/r419/judge-cache-r419-qwen235.jsonl` (110 entries, **0 degraded**):

| axis | value | us (Aug-25 official) | 2026 frontier | gap → frontier |
| :--- | ---: | ---: | ---: | ---: |
| ans_correctness_loose | 94.15 | 89.9 | 92.0 | **+2.2 BEATS** |
| ans_correctness_strict | 90.91 | 80.0 | 84.8 | **+6.1 BEATS** |
| ans_conciseness | 44.19 | 45.2 | 71.8 | −27.6 |
| ref_correctness_loose | 96.08 | 89.5 | 94.6 | **+1.5 BEATS** |
| ref_correctness_strict | 70.59 | 70.7 | 74.1 | −3.5 |
| ref_conciseness | 44.79 | 49.8 | 58.5 | −13.7 |
| regulatory_tone | 93.64 | 96.1 | 100.0 | −6.4 |
| resp_speed | 70.83 | 85.7 | 86.7 | −15.9 |
| **OVERALL (geo mean)** | **72.48** | 73.4 | 81.7 | −9.2 |

Min–max across the judge's 3 repetitions: Ans Cor L 93.9–94.7 · Ans Cor S 90.0–90.9 ·
Tone 93.6–94.5 · Overall 72.4–72.6. Repro check: re-scoring the SAME ckpt from the SAME cache
(`--label r419-repro`) returns the identical axes, so the board is a property of the artifacts.

### The finding that explains the three red axes: the generator changed

`ans_conciseness` is `min(1, len(reference)/len(candidate))` (`evals/official/rubric.py`), a pure
character ratio. This board's **mean answer is 2137.9 chars against a 649.3-char reference**, so
the axis is arithmetically pinned near 45. The R407 hard board's `ans_conciseness` of 84.5 came
from a **757-char** mean answer — because R407's rows were served by Qwen-on-Bedrock while R419's
are served by the **primary leg (Claude opus-5)**, whose answers run ~3x longer.

So R419 is **not a controlled comparison against R407**: same benchmark, different generator. It
is the honest board for the shipping configuration, and it says the top remaining lever is
**answer verbosity at generation** — which is what R407's own §4 concluded and what every post-hoc
reference-pruning lever has failed to move.

## 3. The three all-False rows, triaged

Only 10 of 110 rows fail any criterion; three fail all of them. They are not one cause:

| row | criteria | cause | mechanism |
| :--- | :--- | :--- | :--- |
| `rg_036` | 0/3 | **transport** | wrapper degenerate 1-token completion → retry → persisted → Bedrock (`api_key_invalid_403`) → tail repair failed → shipped a 793-char deterministic draft where turn 1 had shipped 1989 chars |
| `rg_037` | 0/6 | **transport** | same path; shipped 1137 chars where turn 1 had shipped 2503 |
| `rg_088` | 0/3 | **capitulation** | primary leg, healthy (~54 s). Turn 1 answered "No, the operator can't just go ahead" — the official adversarial pushback flipped it to "Yes, the operator can go ahead", against the criteria. Tone also failed (self-referential advocacy) |

`rg_036`/`rg_037` are the *R420 defect*: the engine shipped an answer **thinner than the one it
had already given**. `rg_088` is the separate, known sycophancy failure mode.

**The wrapper diagnosis is confirmed working as designed** — the log shows the R418 guard doing
its job (`wrapper_degenerate_completion` → retry once → `wrapper_degenerate_completion_persisted`
→ raise → Bedrock leg). The loss is not the guard; it is that the documented fallback chain is
**dead in this environment** (`api_key_invalid_403` on all five Bedrock models), so the chain ends
in the deterministic draft. That is an operator credential issue, not a code defect.

## 4. Shipped fix — R420, the prior-answer floor (never regress on the pushback)

`_guard_stage2_truncation` had exactly one last rung: ship the deterministic Stage-1 draft. On a
pushback turn the conversation already holds the answer the engine gave to the **same** question,
so if that answer dominates the draft, regressing to the draft is a pure loss.

**Measured** (published instrument, same criteria, `evals/bench/results/official-r419-priorfloor-hard.ckpt.jsonl`,
cache `judge-cache-r419-priorfloor.jsonl`): re-judging the TURN-1 answers of the 4 deterministic-leg
rows gives **12/12 criteria**, against **4/12** for the drafts:

| row | draft | turn 1 | refs: draft → turn 1 | expected |
| :--- | ---: | ---: | :--- | :--- |
| `rg_036` | 0/3 | **2/3** | `Article 10.4` → `Article 10.2, Article 42.1` | `Article 42.1` (recovered) |
| `rg_037` | 0/6 | **6/6** | `Article 6.2, 49.4` → `49.4, Annex III.7.b, 71.5, 74.3, Annex VIII.12` | `Annex VIII.a` (recovered) |
| `rg_085` | 1/4 | 1/4 | unchanged | no fire (equal length) |
| `rg_092` | 3/3 | 3/3 | unchanged | no fire (equal length) |

Projected on this board: `ans_loose` **94.15 → 96.28** (+2.13 pp), `ans_strict` **90.91 → 91.82**
(+0.91 pp), and the two gold heads restored. The floor fires only when the prior answer is
complete, ≥400 chars, and ≥1.2x the draft, so it is inert on the 2 rows where the texts are equal.

Wiring (all in the same commit as this record):

* `REGENOLD_STAGE2_PRIOR_ANSWER_FLOOR` (default **1**) · `REGENOLD_STAGE2_PRIOR_ANSWER_FLOOR_RATIO`
  (default 1.2) — registered in `_engine_cache_key` (R30/R56/R79 doctrine).
* the serve is labelled `stage2_served_by="prior_turn"` — a **degradation label** that overrides an
  earlier `primary` marking, and the route **refuses to cache it** (R417 policy, plus
  `stage2_call_failed=True` so the refusal does not hinge on the label alone).
* `tests/test_r420_prior_answer_floor.py` — 15 tests (the reading aid, its bounds, the flag, the
  guard's last rung, the label's stickiness, the route's cache gate and key).

## 5. Artifacts

| path | what |
| :--- | :--- |
| `evals/bench/results/official-r419-hard-hard.ckpt.jsonl` | the 110 live rows |
| `docs/measurements/r419/judge-cache-r419-qwen235.jsonl` | 110 judged entries, 3 live reps each |
| `docs/measurements/r388/score-r419-hard-hard.json` | the board (432 KB, per-criterion verdicts) |
| `docs/measurements/r388/score-r419-repro-hard.json` | the cache-only reproduction |
| `docs/measurements/r388/score-r419-priorfloor-hard.json` | the turn-1 re-judge behind R420 |
| `docs/measurements/r419/live_hard_read.json` | judge-free half: ref axes, leg mix, gold heads, latency |
| `docs/reports/r419-live-hard-questions-and-answers.md` | all 110 questions, turn-1 and pushback answers, verdicts |
| `docs/measurements/r388/score-r419-*.VOID.json` | the VOIDed runs (3 dead judge rows, 1/2 on a probe) — kept so a void can never be read as a null |

Judge-side fixes shipped with this round: the OpenRouter transport as a first-class
`--judge-provider` label (the wrapper's Claude Code session was down and the Bedrock token was
rejected), and a parser fix — `_parse`'s fallback sliced first-`[`-to-last-`]` and returned the
INNER verdicts array as the payload, so a valid grouped judgement was recorded as "no live run"
and scored all-False. Every complete JSON value is now decoded in order and multiple objects are
merged; a second retry runs the SAME prompt at a larger output budget
(`tests/test_r419_judge_payload_parse.py`).

## 6. Open items

1. **`rg_088` pushback capitulation** (turn-1 verdict correct, pushback reversed it). `REGENOLD_PUSHBACK_KEEP_CONTRACT`
   exists and is default OFF; this row is the cost of that default.
2. **Answer verbosity** — the −27.6 pp conciseness gap is generation-side. R380's Prompt V3 moved
   it (−20 % length, +8 pp ref conciseness) but was defaulted OFF for dropping 7 gold heads; it
   needs a redesign that holds the enumerated limbs while shortening prose.
3. **Restore the Bedrock credentials** so the documented fallback chain is a chain again.
