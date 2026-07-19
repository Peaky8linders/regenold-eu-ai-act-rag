# R282 — Deferred-task closeout: pair-rescue A/B (rejected), R281 easy live-confirm, wrapper system-prompt A/B (rejected)

**Session:** 2026-07-19. Closed the three R281-deferred items, each **correctly
gated** (env-gated, A/B'd via the gold-bearing `easyhard_ab` / the pairwise judge,
never a blind flip). **Two of three A/Bs REJECTED their flip** — both ship gated
default-OFF with the measured reason recorded. All regression gates byte-identical
to R281 HEAD `125f6d4`.

---

## Task A — R282 Art 6 ↔ Annex III pair-rescue in `adaptive_ref_clamp` (REJECTED → default OFF)

`app/routes/regenold.py::adaptive_ref_clamp` gains an env-gated
(`REGENOLD_CLAMP_PAIR_RESCUE`, **default OFF**) refinement: when a member of the
Art 6 ↔ Annex III high-risk pair is kept in the clamp head but the budget dropped
its partner into the tail, rescue the partner (Art 6(2) classifies high-risk VIA an
Annex III use case, so shipping one without the other is incomplete). Stage2-gated
+ absent from the engine cache key (R79), like the parent R281 clamp.

**Gold-bearing A/B** (`easyhard_ab --local` n=132, live Claude Max, clamp ON in
both arms so the pair-rescue is the only variable; 0 errors) — sidecar
`easyhard-r282-pairrescue.json`:

| split | ref_loose (recall) | ref_strict (F1) | ref_conc | est. Overall |
| ----- | ------------------ | --------------- | -------- | ------------ |
| hard n=37 | +0.0135 (mt_v4_005 gold Annex III recovered, as designed) | +0.0009 | −0.0118 | **+0.02 pp (wash)** |
| easy n=95 | +0.0053 | **−0.0088** | **−0.0315** (pred:gold 1.55→1.62) | **−0.46 pp** |

The rare gold-pair recall gain does NOT outweigh the precision cost on the many
rows where Annex III / Art 6 is over-citation noise. **Net rubric-negative → stays
OFF** (the R142.1 / R280 discipline). Kept as a documented off-switch:
`REGENOLD_CLAMP_PAIR_RESCUE=1` buys mt_v4_005-style pair recall at the measured
precision cost. +21 tests (`test_r282_pair_rescue.py`).

## Task B — R281 clamp easy-split LIVE confirmation (belt-and-suspenders; CONFIRMS default-ON)

The R281 gold-protected clamp shipped default-ON on the hard-split live A/B
(+1.17pp) + the easy-split OFFLINE sim (+1.9pp). This round ran the **live** easy
A/B (`REGENOLD_ADAPTIVE_REF_CLAMP` 0 vs 1, easy n=95). The full run was
rate-limit-contaminated — the branch arm burst 36 `http_429` on cache-miss
`tricky_v2` rows (the wrapper's 10/min limit; the Claude Max quota itself is fine —
the steady baseline arm had 0 errors). Salvaged the valid **paired** comparison on
the 59 both-OK rows:

| axis | OFF | ON | delta |
| ---- | --- | -- | ----- |
| ref_loose (recall) | 0.8672 | 0.8333 | −0.0339 |
| ref_strict (F1) | 0.5754 | 0.6358 | **+0.0603** |
| ref_conc | 0.3591 | 0.5031 | **+0.1441** |
| kw_recall | 0.7401 | 0.7401 | +0.0000 (shared cache ⇒ clamp is the only variable — validates the pairing) |
| **est. Overall** | | | **+2.34 pp** |

Consistent with and exceeding the +1.9pp offline sim. **R281 default-ON confirmed
on easy** (no code change). Harness note: `easyhard_ab`'s `_report` header prints
only the BASELINE error count, which hid the branch 429s — read the sidecar's
per-arm error counts, not the header.

## Task C — wrapper system-prompt fix A/B (REJECTED → keep OFF, do NOT activate)

The deferred `claude_cli.py` bug: the wrapper passed the caller's system prompt as
`{"type":"text",...}`, which `claude_agent_sdk 0.2.82` (typed
`system_prompt: str | SystemPromptPreset | SystemPromptFile | None`) **silently
drops** — so `ANSWER_GENERATE_SYSTEM` (~12.8K tokens) reached the model **0% of the
time**. Verified empirically: a "reply only ARRR" system prompt → the prod wrapper
(8000) returns "4" (dropped); the patched wrapper (8001) returns "ARRR" (forwarded).
Gated fix in `src/claude_cli.py` on `WRAPPER_FORWARD_SYSTEM_PROMPT`, **default OFF**
= byte-identical to prod.

**A/B** (two wrapper instances — prod 8000 = system DROPPED, patched 8001 =
FORWARDED; two `easyhard_ab` scorecards n=40 easy, fusion OFF to isolate the
single-provider wrapper path; 0 errors) — sidecars `easyhard-t1-sysprompt-{off,on}.json`:

| axis | OFF (dropped, = prod) | ON (forwarded, = fix) | delta |
| ---- | --------------------- | --------------------- | ----- |
| kw_recall | **0.8750** | **0.6083** | **−0.267** |
| ref_loose | 0.8542 | 0.7500 | −0.104 |
| ref_strict (F1) | 0.6455 | 0.4901 | −0.155 |
| ref_conc | 0.5391 | 0.3876 | −0.152 |
| tone | 1.0 | 1.0 | 0.0 |
| pred:gold | 1.83 | 2.50 | +0.67 |
| latency p50 | 22.1s | 5.4s | −16.7s |

**Pairwise judge** (Sonnet 4.6, position-swapped, `pairwise_from_answers` over the
two sidecars; stopped at n=8 — a clean sweep): **baseline/OFF wins ALL 4 axes on
8/8 rows** (branch/ON win-rate 0.000, sign-test p≈0.008 per axis). Fully confirms
the scorecard.

**Forwarding the system prompt is strongly rubric-NEGATIVE on every axis.** Root
cause (from the answers): the 12.8K-token `ANSWER_GENERATE_SYSTEM` OVERWHELMS the
specific question — answers **drift off-topic** (a workplace-emotion-inference
question drifts into "real-time remote biometric identification by law
enforcement"; a biometric-categorisation question mis-cites Art 2/27/49 instead of
gold Art 5), get terser (median 830c vs 1107c, 31/40 rows <8s), and over-cite
generically (pred:gold ↑). **Decision: keep OFF — do NOT activate.**

**The load-bearing finding**: `ANSWER_GENERATE_SYSTEM` was NEVER reaching the model,
so every prompt-engineering round (incl. R277's minimal-composer, whose "46/51
ties" now make sense) tuned a DEAD prompt. Activating it as-is HURTS. This reframes
the R280 answer-composition bottleneck: the good answers come from the engine's
user-message (references + query profile + cross-references), NOT the system prompt.
Any future attempt to feed the model composition instructions must RE-AUTHOR them
for the system-prompt role and re-A/B — the current one, activated as-is, causes
drift. The wrapper fix + `DEPLOY_SYSTEM_PROMPT_FIX.md` are committed to the LOCAL
wrapper repo (default OFF); no operator restart is warranted.

---

## Gates (all green — deterministic, byte-identical to R281 HEAD 125f6d4)

* davidath QA: Ans Strict **0.4037** / Ref Loose **0.8394** / Ref Strict **0.5543**
  / Tone 1.0 — byte-identical (Task A is default-OFF + stage2-gated → inert on the
  `provider=cli` bench; Task C is wrapper-only, not in the regenold repo).
* Full unit suite: **4922 pass, 1 skip, 88 fail** — the 88 are the documented
  pre-existing `provider=cli` + `EXTERNAL_EMBEDDINGS=0` env artifacts; the failure
  set is **byte-identical to clean HEAD** (`diff` empty — 0 new, 0 fixed).
* 276-runner all categories **100%**; OOS probe **21/21, 0 leaks**.
* New eval infra: `evals/harness/pairwise_from_answers.py` — pairwise-judges two
  pre-captured answer sets, the cross-process A/B path the wrapper-provider
  singleton's construction-time `OPENAI_API_BASE` binding forces (can't toggle base
  in-process → two wrapper instances + separate capture processes).

## Net wire change: NONE

Both A/Bs rejected their flip; both ship gated default-OFF. Regenold merges the
gated pair-rescue option + the docstring decision record + the reusable eval helper
+ tests (wire byte-identical to R281). The wrapper fix is committed local-only,
default OFF, recommended to stay OFF.
