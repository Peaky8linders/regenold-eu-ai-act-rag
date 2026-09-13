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
* **Now measured on the criteria-bearing corpus too** — see
  `CHECKPOINT-official-gate.md`. On the reconstructed official gold, the lever's
  easy-half effect over the 26 rows it actually reaches is: `ans_conc`
  **+19.2 pp**, `ref_conc` **+11.2 pp**, `resp_speed` **+3.8 pp**, offset by
  `ans_loose` **−2.2 pp** and `ans_strict` **−7.7 pp** — two rows losing one
  criterion each — for **OVERALL +6.1 pp** (64.9 → 71.0). Board-weighted by reach
  this is ×1.047 on the geomean (`≈ +3.4 pp` at a board value of 72). The loss is
  real content: the aim clause of Art. 14 (`rg_010`) and the scope of "without
  undue delay" (`rg_045`) do not survive a 41% compression.

## 5. Live production confirmation (deploy `dfea832308de`)

The same question asked to production twice — once as a first ask, once with a
9-turn preamble (the official hard shape):

| ask | answer chars | refs |
| :--- | ---: | :--- |
| single-turn | **2065** | `Article 11.1`, `Annex IV.2`, `Annex I`, `Article 17.1`, `Article 47.1`, `Annex V.2` |
| multi-turn (9 prior turns) | **4802** | `Article 11.1`, `Annex IV.2`, `Article 9.2`, `Article 47.1`, `Article 16` |

The multi-turn answer is **2.3× longer**, which is the observable live signature
of the invariance: the single-turn ask is served the full system (the R383/R411
mechanism compresses the answer to ~0.199×), the multi-turn ask keeps the persona
and answers at length — and the two share their operative references
(`Article 11.1`, `Annex IV.2`). An earlier skip of this check would have been a
misread: a shorter multi-turn answer would have looked like the lever leaking
into hard mode.

## 6. Honest residuals

* The correctness axes (`Ans Loose/Strict`) were NOT re-judged **in this pass**,
  and §6 first blamed the wrong thing for it (the wrapper judge's expired OAuth).
  They were subsequently judged on the criteria-bearing corpus — see
  `CHECKPOINT-official-gate.md` §5 — so what follows is the reason the *probe*
  corpus could never have answered them, not an open gap.
  Corrected, because the reason changes what a future attempt should do: the
  binding constraint is the **corpus**, not the judge. Both gates here run on the
  harness probe corpus (`paper_st_v4` / `paper_tricky_v4` / `multiarticle_r268`),
  which carries `expected_refs` and `expected_keywords` per row but **no
  correctness criteria** — there is nothing to judge against. Measured: **0 of the
  95 easy probe questions appear in `official_gold_n110.jsonl`**. A working judge
  would not have helped; the criteria-bearing corpus is the reconstructed official
  gold, which is what `docs/measurements/r415/official_lever_gate.py` uses.
  Reference axes and latency are judge-free and are the ones quoted above.
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
* **A large share of the graded board never reaches the model at all.** The
  whole-board sweep (§7) found rows answered in ~4 s with **zero** Stage-2
  attempts — curated deterministic intercepts. The single-turn lever edits the
  system slot of a model call, so on those rows it is inert *by construction*, and
  a contiguous convenience slice of the corpus is dominated by them (4 of the
  first 6). That is why §7 pairs on the reachable subset instead of a slice, and
  it is a reach fact about the board rather than about the lever.
