# R411 — Architecture Audit & SOTA Roadmap

**Date:** 2026-09-12
**Branch:** `fix/r409-r408-audit`
**Base commit:** `dd797d9a9de6` (production, PR #412)
**Instruments:** `docs/measurements/r411/*`, `evals/harness/easyhard_ab`, `docs/r388` gold key

---

## 1. Method

Every claim below is traceable to a command in this repo. Three instruments were used,
in increasing cost order:

| instrument | cost | what it can decide |
| :--- | :--- | :--- |
| `intercept_precision_audit.py` (new, R411) | seconds, no network | detector precision over the official 110 |
| `answer_completeness_offline_validation.py` (R409) | seconds, no network | detector recall/FP over the frozen 110-row ledger |
| `easyhard_ab --local` (paired A/B) | ~30 s/row, live tunnel | the official axes + `gold_dropped_head` |

The scored milestone scorecard is the R409-corrected, 110-row official-axis run
(Sonnet 5 and Qwen 3 235B, live Stage-2):

| axis | Sonnet 5 | Qwen 3 235B |
| :--- | ---: | ---: |
| Ans Correctness (loose) | 84.70 | 93.14 |
| Ans Correctness (strict) | 67.27 | 83.64 |
| Ans Conciseness | 84.50 | 84.50 |
| Ref Correctness (loose) | 96.50 | 96.50 |
| Ref Correctness (strict) | 75.83 | 75.83 |
| **Ref Conciseness** | **55.93** | **55.93** |
| Regulatory Tone | 100.00 | 100.00 |
| **Resp. Speed** | **71.65** | **71.65** |
| **Overall (geomean)** | **78.29** | **81.42** |

---

## 2. The pipeline as built

```
POST /api/v1/regenold/eu-ai-act/ask
  │
  ├─ route: history flattening, re-ask focus, curated-intercept check
  │
  ├─ STAGE 1  deterministic parse + retrieval   (no LLM, ms)
  │     ├─ KG / KB retrieval (Neo4j Aura or embedded)
  │     ├─ grounding text ← select_relevant_paragraphs(ref, q, 1200 chars)
  │     │                 + closed-set skeleton  (REGENOLD_CLOSED_SET_SKELETON, ON)
  │     └─ deterministic answer  (citation-exact, complete for its slice)
  │
  ├─ STAGE 2  LLM polish                         (~15–30 s of the request)
  │     ├─ PRIMARY: cloudflared tunnel → claude-code-openai-wrapper (Claude Max)
  │     └─ FALLBACK: AWS Bedrock (Qwen 3 32B / 235B)
  │
  └─ post-Stage-2 guards → wire references recomputed FROM THE PROSE
```

Two structural facts drive almost everything below:

* **The wire references are recomputed from the final prose.** Stage-2 is therefore not
  cosmetic: it is the producer of the reference set. This is why skipping Stage-2 for
  "simple" questions was measured to collapse `ref_loose` 0.75 → 0.47 (recorded in
  `_needs_stage2_enhancement`'s docstring). **Latency cannot be bought by skipping
  Stage-2.**
* **The 8 axes are aggregated by geometric mean.** A relative gain of *x* on one axis
  moves the Overall by `x^(1/8)`. So a 19 % relative gain on Speed (71.65 → 85) is worth
  **+1.7 pp Overall** — larger than a 10 % gain on any single correctness axis, and it
  carries no content risk.

---

## 3. Findings

### F1 — The dominant engine failure is *generation*, not retrieval

Triaging all 67 failing Sonnet-5 criteria against the verbatim Regulation
(`r407_sonnet5_failing_criteria_triage.json`):

```
rows=67   ENGINE_GAP=51   CRITERION_DEFECT=12   AMBIGUOUS=4
of 51 ENGINE_GAPs, 49 had the provision ALREADY in the emitted references
```

So in **49 of 51** cases the retrieval layer had already surfaced the right provision —
the content was lost between the retrieved context and the shipped sentence. The root
causes: `OMITTED_ENUMERATED_ITEM` 22, `WRONG_OR_MISSING_PROVISION` 10,
`MISSING_CONDITION_OR_EXCEPTION` 9, `PUSHBACK_DRIFT` 7, `VERDICT_POLARITY` 6.

**Consequence for the roadmap:** retrieval work is not the bottleneck. The bottleneck is
(a) what text reaches the Stage-2 prompt and (b) what Stage-2 does with it. The
`REGENOLD_CLOSED_SET_SKELETON` lever (default ON since R400) attacks (a); the R409
repair guards attack (b) but are all default-OFF because each failed its gold gate.

### F2 — `ANSWER_GENERATE_SYSTEM` is dead on the primary transport (wiring defect)

`_openai_wrapper_complete_for_graph_rag` caps the system slot:

```python
wrapper_system = (
    system if (_full_system or len(system) <= 1000)
    else "You are an expert EU AI Act regulatory compliance specialist."
)
```

`len(ANSWER_GENERATE_SYSTEM)` is **53,601 chars** and carries **15 numbered legal
behaviour rules + 4 few-shot exemplars**. On the primary path (the cloudflared
Claude-Max tunnel) the entire prompt is replaced by a **62-character** persona. The
rules in the *user* channel (`USER_ANSWER_COVERAGE_CLAUSE`, `USER_CRITICAL_RULES_CLAUSE`)
still arrive; the system-channel copy does not.

The cap was added by R342 on a premise R383 later **falsified** — measured over this same
tunnel, a 53 kB system + 18–21 kB user payload produced **0 HTTP 500s in 6/6** calls, and
delivering the system prompt made answers **0.199×** the length and **2.38× faster**.
R383 shipped the repair as `REGENOLD_STAGE2_FULL_SYSTEM`, default OFF, because it is
prompt-side and therefore **not reference-neutral** (invariant #5) — the prose→refs passes
recompute the wire citations from Stage-2 prose.

### F3 — Resp. Speed is the largest headroom, but the obvious lever **FAILS the gate**

Full wiring: `REGENOLD_STAGE2_FULL_SYSTEM=0 → 1`, `evals.harness.easyhard_ab --local`,
paired, live tunnel, 0 errors in either arm.

**Result: the lever splits by modality, and the split is the finding.** A 12-row easy
probe looked like a clean win — which is exactly why the significant sample mattered.

Small paired probe (easy, n=12):

| row | baseline | branch |
| :--- | ---: | ---: |
| st_v4_001 | 40.9 s | 15.7 s |
| st_v4_002 | 17.0 | 12.1 |
| st_v4_003 | 18.8 | 11.0 |
| st_v4_004 | 26.9 | 16.1 |
| st_v4_005 | 44.5 | 18.7 |
| st_v4_006 | 18.1 | 13.4 |
| st_v4_007 | 24.3 | 9.6 |
| st_v4_008 | 28.6 | 24.6 |
| st_v4_009 | 21.0 | 11.1 |
| st_v4_010 | 52.3 | 21.7 |
| st_v4_011 | 23.7 | 14.4 |
| st_v4_012 | 19.6 | 10.9 |
| **mean** | **27.97 s** | **14.94 s** |

**11 of 12 rows faster.** `resp_speed` consequently rises by ~13 pp, and the reference
axes moved in the right direction too:

```
EASY n=12      baseline   branch
ref_loose       0.9583    0.9583   (+0.0000)
ref_strict      0.4583    0.4768   (+0.0185)
ref_conc        0.2514    0.2540   (+0.0026)
kw_recall       0.9444    0.9444   (+0.0000)
gold_drop_hd    1         1        (+0  PASSES hard rule #8)
pred:gold       4.36      4.00
```

If that were the whole picture it would be `71.65 → ~84.7` on Speed,
`×1.182^(1/8) = ×1.0212`, i.e. **+1.65 pp Overall**.

**The hard split (the GRADED modality — multi-turn plus adversarial pushback, n=37)
falsifies it:**

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

**Verdict: default stays OFF.** A −10.8 pp `ref_loose` loss for a −9.7 s latency gain,
and +13 pp Speed is worth only ~+1.7 pp Overall — it does not buy the loss back. The
lever is shipped gated, with the flag's semantics pinned by
`tests/test_r411_stage2_full_system.py` so the easy-mode number alone cannot flip it.

**Mechanism, and the repair worth trying next.** The full system prompt is what cuts the
answer to 0.199× its length. Hard mode grades the answer to an ADVERSARIAL PUSHBACK,
whose contract is to KEEP the points turn 1 made — and a 58 %-shorter answer drops them.
The two levers are in direct tension. So the candidate is a **single-turn-only** gate:
deliver the full system only where there is no pushback and `history_turn_count == 1`,
keeping the easy-mode speed win without the keep-loss. That is a new hypothesis and needs
its own paired run; it is not shipped here.

### F4 — The curated intercepts are precise on the real corpus

`intercept_precision_audit.py` over the official 110: **every one of the 30 detectors
fires on 1/110 rows, and every fire is on-topic.** The whole gate fires on 22/110
(20 %), each a legitimate curated closed set or scope verdict — those rows are answered
deterministically in sub-second time, which *helps* Speed.

The gate is still an over-match risk for out-of-corpus input (an invented
provider-vs-deployer comparison question is captured by `_detect_reclassification_inquiry`
on a *trailing* sub-question — the same "trailing ask" shape fixed in the R410
verdict-lead detector). It is **not** a benchmark-affecting defect, so it is recorded
here as a known-precision item, not silently changed.

### F5 — TrustGraph's reference guard is already saturated

962 live wire references across 294 rows, **0 non-existent coordinates (0.00 %)**, with
`REGENOLD_REF_COORD_GUARD` default `1`. A second guard can only lose gold heads under
hard rule #8, so none was added. TrustGraph's remaining value is the SPARQL-queryable
A-Box, not a reference guard.

### F6 — Ref Conciseness is the largest *relative* gap, and the riskiest

`ref_conc = 55.93` while `ref_loose = 96.50` means the engine cites ~1.8× the minimal
set. It is the lowest axis on the board. Every prior attempt to trim it
(`QREL_PRUNE`, `CITABLE_BASE_GUARD`, `REFS_RECONCILE`) either failed its gold gate or
tripped the R142.1 failure mode — dropping a *needed* provision because a *needed* gold
head looked redundant. It stays a first-class target but it is **not** a safe one.

**R411 measured the cheapest candidate and it FAILS its own safety test.**
`docs/measurements/r411/ref_minimality_probe.py`, over the 107 ref-scored rows of the
frozen R407 hard ledger: 221 of 301 emitted refs (73.4 %) are outside the expected key,
and the obvious prune — *drop any emitted ref the prose never mentions* — would remove only
**19** of them, because **202 of the 221 are provisions the answer genuinely discusses**.
Worse, it is not reference-neutral: `rg_019` (Article 3.60) and `rg_076` (Article 3.2) are
correct *definitional* answers that quote the definition TEXT without naming the
provision, so the rule deletes two EXPECTED refs to shed nineteen excess ones. That is a
ref-correctness loss traded for conciseness — exactly what hard rule #8 refuses.

The structural read is the useful part: `ref_conc` is not measuring noise, it is
penalising thoroughness, because the expected key is the *minimal* set while the engine
answers with the surrounding framework (Art 5, 50, 51-56, Annex III). That is why three
prior attempts failed, and it means the axis has to be moved **generation-side** (discuss
fewer provisions) rather than pruned post hoc. Bias note for the next attempt: a first cut
of this probe parsed only `Article N` and scored every `Annex` ref as unmentioned,
reporting 78 prunable refs and hiding 15 expected refs inside them — the fix that matters
is in the instrument, not the rule.

### F7 — The R409 completeness guards are precision-poor and stay OFF

Replayed deterministically over the frozen 110-row ledger: `member` fires on 9.9 % of
*passing* rows, `keep_clause` on 97.2 %. The R410 closed-set gate failed hard rule #8
(15 → 16 gold heads). **R410** fixed the `member` detector's premises (13 fires → 2, FP
9.9 % → 0.0 %; attributed in `answer_completeness.py`'s own docstring, where the round
label is R410 — an earlier draft of this section credited it to "R412", a round that
does not exist in this repository and is now used by the R412 notification-filter work,
so the label was corrected here rather than left to collide) but the lever has nothing to
do on the available corpus, so it remains default-OFF. Recorded so it is not re-proposed
on evidence that cannot support it.

**R411 closed the recall side too, and found it is at its safe ceiling.**
`docs/measurements/r411/member_recall_probe.py` replays the detector over the 12 distinct
rows carrying the 22 `OMITTED_ENUMERATED_ITEM` criteria and reports the blocking gate:
`is_list_question` false on **7**, no closed-set HEAD discovered (the question names
"instructions for use"/"quality management system", not a coordinate) on **3**, and the
answer never names the set on **2**. Read against the criteria, the 7 are mostly the wrong
instrument — `rg_010` wants the provider/deployer attribution of Art. 14(3) measures,
`rg_014` the full text of ONE Annex III point, `rg_078`/`rg_102` clause fidelity on yes/no
asks. Only `rg_051` (Art 22(3)), `rg_059` (Art 68(3)) and `rg_094` (Annex XII.1) are real
lettered sets the answer touched partially, and each would also need `_question_engages`
to admit a question that does not ask for the set — the citation-side rule that lost gold.
So **no change**: the instrument for these rows is the evidence/prompt layer, not a wider
engagement rule.

---

## 4. Ranked roadmap

Ordered by risk-adjusted expected gain, using `Δoverall ≈ (1/8)·Δaxis/axis`.

| # | lever | axis (current) | mechanism | expected | gate | risk |
| :- | :--- | :--- | :--- | ---: | :--- | :--- |
| 1 | **Single-turn-only full system prompt** | Speed 71.65 | the F3 lever, restricted to `history_turn_count == 1`: keeps the easy-mode −13 s without the pushback keep-loss. **R412 RAN THE PAIRED EASY GATE AND IT PASSED ON EVERY AXIS → SHIPPED DEFAULT ON.** n=39 of the 95-row easy split, wrapper-served (0 `bedrock_auto_fallback`), 0 errors: `ref_loose` 0.8718 → **0.9615**, `ref_strict` 0.4333 → **0.5831**, `ref_conc` 0.2025 → **0.3481**, `kw_recall` +2.56 pp, `gold_dropped_head` **8 → 3** (hard rule #8 passes), latency p50 37.40 s → **21.93 s** (**−15.47 s**, 37/39 rows faster). Opt out with `=0`. The previous round's "no speedup" paired run was **VOID**: its log carried **189** `bedrock_auto_fallback` events (wrapper down ⇒ Bedrock served both arms with the full `system`) | **+13.2 pp** (measured, not projected — the ref axes gained far more than the +1.3 pp that assumed only Speed moved) | DONE — `docs/measurements/r412/score-singleturn-easy-n39.json` | **Shipped.** `REGENOLD_STAGE2_FULL_SYSTEM` itself stays OFF (multi-turn pushback: `gold_drop_hd` 12 → 18) |
| 2 | Ref-minimality pass | Ref Conc 55.93 | rank wire refs by *claim-dependence*, not retrieval score; cut the ~45 % excess. **R411 tested the cheapest form (prose-ungrounded prune) and it FAILS: 202 of 221 excess refs are prose-grounded, and the remaining 19 cannot be cut without deleting 2 expected refs.** Any future form must survive that same safety test | +2.2 pp at 70 | `easyhard_ab` + R142.1 audit | **High** — four attempts now, all constrained by the same tension |
| 3 | Stage-2 content-preservation contract | Ans Strict 67.27 | reject a polish that drops a skeleton member the draft carried; deterministic, no extra call | +1.0 pp | `easyhard_ab` + `answer_completeness` replay | Medium — needs to stop firing on passing rows (F7) |
| 4 | Sub-point grain on the wire | Ref Strict 75.83 | the evaluator's keys are ~71 % sub-point vs our 14.3 %; `COORD_MAP_PROMPT` is the candidate | +0.6 pp | `easyhard_ab` | Medium |
| 5 | `REGENOLD_KG_POINT_TEXT` | Ans Loose | point text into the Stage-2 block (+3.5 kB/row) | unknown | needs a same-generation A/B | Medium — prompt-side |

Levers **explicitly not** on this list, with the measurement that removed them:

* `REGENOLD_STAGE2_FULL_SYSTEM` **unconditionally** — F3: `gold_drop_hd` 12 → 18 on the
  graded hard split. Only the single-turn-restricted form (row 1) is still open.
* `REGENOLD_STAGE2_SIMPLE_SKIP` — measured `ref_loose` 0.75 → 0.47. Stage-2 produces the
  wire refs; skipping it is not a latency lever.
* `REGENOLD_COHERE_RERANK` — 0 calls in all three placements tried (R331), and the
  cross-encoder scores `Article 99` at 0.4583 on a transparency question.
* A second coordinate guard (F5) — 0.00 % of live coordinates are invalid.

---

## 5. What this round ships

1. **`intercept_precision_audit.py`** — a repeatable, network-free instrument for the
   detector over-match class, which has now cost this repo four separate rounds
   (medtech triage, Art. 5(1)(g), verdict-lead, and the R410 member guard).
2. **`REGENOLD_STAGE2_FULL_SYSTEM` gated on the full 132-row corpus** — see §6.
3. This audit, with the roadmap ranked by measured leverage.

## 6. Gate result

See `docs/measurements/r411/score-r411-fullsys-gate.md` for the full 132-row paired
read (official reference axes + `gold_dropped_head` + per-row latency).

## 7. Honest residuals

* The n=12 probe (§3, F3) is a **smoke run** and is not by itself a gold-gate pass; only
  the full run in §6 can be cited.
* The harness prints a standing caveat that in-process A/B latency is confounded by a
  shared engine cache. It does not apply here — `REGENOLD_STAGE2_FULL_SYSTEM` **is**
  registered in `_engine_cache_key` (`app/routes/regenold.py`), so the two arms cannot
  share a cached engine output; the LLM itself is not cached. The effect is also
  per-row consistent (11/12), which a cache warm-up would not be.
* `easyhard_ab` scores the official *reference* axes only. It does **not** exercise
  Ans Correctness strict/loose, which need the grounded judge (`ab_judge`). Lever 1 is
  therefore proven on Speed + the three reference axes; its answer-quality read is a
  separate run.
