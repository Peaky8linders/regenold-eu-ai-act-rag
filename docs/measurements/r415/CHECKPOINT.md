# R415 — the pushback path under the default-ON single-turn lever

**Date:** 2026-09-12  **Branch:** `fix/r409-r408-audit`
**Question:** `REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN` is default ON (R412). Confirm
the multi-turn (hard) pushback path is untouched end to end, and quantify the
combined board movement.

---

## 1. The instrument, and the two ways it was wrong first

`docs/measurements/r415/pushback_invariance_probe.py` drives the REAL request path
(route → history flattening → engine → provider) over probe rows and records, per
arm, (a) the kwargs the route threaded and (b) the system payload the model would
receive. Two wrong seams were built and discarded, and both are recorded because
each produced a *confident wrong answer*:

1. **The engine function.** Replacing
   `_openai_wrapper_complete_for_graph_rag` records the PRE-substitution text, so
   the two arms read `5000` vs `5000` and the probe reported "identical
   everywhere". The substitution happens INSIDE that function. This is the trap
   `evals.harness.gate_validity` already documents in its own docstring — walked
   into again.
2. **The provider singleton with no `.env`.** Without `P2P_GRAPH_RAG_PROVIDER`
   the wrapper leg is not the one in use, so the seam never sees the lever and the
   non-vacuity control fails. The probe now REFUSES to run in that state (exit 2)
   instead of reporting a vacuous "no change".

The working instrumentation is BOTH seams at once: the provider singleton records
the payload (the truth), and a pass-through wrapper on the engine function records
what the route threaded and then delegates to the real body.

Third pitfall, handled rather than hidden: the pipeline's own call count varies
between two sequential runs of the same row (measured: the same row moved when
Groq answered `429` on tokens-per-day, and Neo4j/Cohere retried). The verdict
therefore compares the **graded call's payload** — the only payload the lever
edits — and reports call-count variance as a note.

## 2. Predicate scope (deterministic, no pipeline)

Long system + one Stage-2 answer call, both arms, for each turn count:

| `history_turn_count` | flag=0 system len | flag=1 system len | identical |
| :--- | ---: | ---: | :--- |
| `None` (modality unknown) | 61 | 61 | yes |
| 0 | 61 | 5000 | **no** |
| 1 | 61 | 5000 | **no** |
| 2 | 61 | 61 | yes |
| 9 | 61 | 61 | yes |

The differ-set is **{0, 1}**, which is the documented predicate `<= 1` — and the
boundary is worth stating precisely, because the in-code comment said "a
single-turn ask reads 1". The route derives it as
`max(0, user+assistant messages - 1)`, so a **first ask reads 0**, an ask with
**one prior exchange reads 1**, a direct engine caller that omits the field gets
`GraphRAGRequest`'s default of **1**, and the official hard final (10 messages)
reads **9** (the pushback 9 or 10). `None` is never single-turn, which is what
keeps the Stage-1 parser and every auxiliary pass out of the lever. The comment is
corrected in `_graph_rag_impl.py`; the behaviour is unchanged.

## 3. End-to-end (real route, 4 hard + 4 easy rows)

| split | route threaded | graded payload, flag ON | graded payload, flag OFF | verdict |
| :--- | :--- | :--- | :--- | :--- |
| hard (×4) | `('Stage 2 (Polishing)', 2)` both arms | 61 chars, sha `3bc63d065b58812b` | identical | **UNTOUCHED** |
| easy (×4) | `('Stage 2 (Polishing)', 1)` both arms | 59644 chars, sha `3e427d7d42b87f11` | 61 chars, sha `3bc63d065b58812b` | **DIFFERS** |

Verdict lines from the run: predicate scope ✓, hard graded payload identical ✓,
hard modality identical ✓, seam fired on every hard row ✓, **non-vacuity control
passed ✓** → `CONCLUSIVE: True`.

The control is the load-bearing half: easy rows must differ under the same
instrument in the same run, or "no change on hard" would be
indistinguishable from an instrument that never fired.

## 4. Combined board movement

* **Hard split: 0, and now by measurement rather than by assumption.** The graded
  payload on a multi-turn ask is byte-identical between the flag's arms, so the
  lever cannot move any hard-split axis. For contrast, the UNCONDITIONAL
  `REGENOLD_STAGE2_FULL_SYSTEM` on that same 37-row hard ledger measured
  `ref_loose` 0.8423 → 0.7342 (**−10.81 pp**), `ref_strict` −4.61 pp, and
  `gold_dropped_head` **12 → 18 (+6)** — a hard-rule-#8 FAIL
  (`docs/measurements/r411/score-r411-fullsys-hard-n37.json`, `live: primary_ok=74
  fallback_ok=1`). That is the damage the single-turn restriction exists to keep
  out, and §3 shows it does.
* **Easy split: the R412 n=39 paired gate, unchanged since** —
  `ref_loose` 0.8718 → **0.9615**, `ref_strict` 0.4333 → **0.5831**,
  `ref_conc` 0.2025 → **0.3481**, `kw_recall` +2.56 pp,
  `gold_dropped_head` **8 → 3**, latency p50 37.40 s → **21.93 s**
  (`docs/measurements/r412/score-singleturn-easy-n39.json`).
* **Combined:** the movement is the easy-half movement; the hard half contributes
  exactly zero because the lever never reaches it.

## 5. Honest residuals

* The correctness axes (`Ans Loose/Strict`) were NOT re-judged in this pass. They
  need the Claude-Max wrapper judge, whose OAuth is expired; the substitute on
  this account is `eu.anthropic.claude-opus-4-6-v1` via Bedrock (Sonnet 4.6 /
  Opus 5 / Sonnet 5 profiles return `api_validation_400`). Reference axes and
  latency are judge-free and are the ones quoted above.
* **The `<= 1` boundary includes `history_turn_count == 1`** — an ask with ONE
  prior exchange also receives the full system. That is by design (it is the
  single-turn-shaped case, and `GraphRAGRequest`'s default is 1), and the official
  hard modality feeds a 9-turn conversation so it is not graded there — but a
  two-message follow-up is the R411 failure shape one turn earlier than the
  graded pushback. Narrowing it would need its own paired gate on a
  one-prior-turn history; it is recorded here as the residual, not changed
  without evidence.
* The probe's hard rows are the harness's `mt_v4` rows and read
  `history_turn_count=2`, not 9. The predicate table covers 9 directly (§2), so
  the graded case is covered even though the end-to-end sample is shallower.
