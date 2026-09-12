# R413 — grammatical tail repair + void-run self-detection

**Date:** 2026-09-12
**Branch:** `fix/r409-r408-audit`
**Carried in from:** R412 (`352f4bfab9af`) — the tail-repair weld was the one
residual that round explicitly did not ship a heuristic for, because a rejection
rule had to first survive the "does it fire on passing rows" test that the F7
guards failed.

---

## 0. Roadmap row 2 (Ref-minimality) — FALSIFIED, see §9

The SOTA-roadmap row after the shipped single-turn lever was *Ref-minimality*.
It is closed by measurement in §9 with a deterministic ceiling instrument, so
read that section as the separate deliverable it is.

---

## 1. What was wrong

`_attempt_stage2_tail_repair` (R357) asked the model for the **missing tail** of a
cut final sentence and concatenated it: `enhanced.rstrip() + tail`. Nothing
checked that the two halves form ONE sentence, so two defects could ship:

* **clause weld** — the cut landed after a closed clause and the model opened a
  new one. R411 production:

  > "... the only EU AI Act transparency duties it triggers are those in
  > answering general patient queries on a hospital website **is neither**
  > emergency triage nor ..."

* **glue (space loss)** — the model was told to continue a mid-word cut with NO
  leading space and a word-boundary cut WITH one, so the boundary decision was
  its to get wrong:

  > "... the provider must **stillregister** the system in the EU database ..."

## 2. The fix

`REGENOLD_STAGE2_TAIL_REPAIR_MODE` selects the arm. `sentence` (new default after
the gate below):

1. split the polish abbreviation-aware (`_split_sentences_text`; the R357
   `_last_sentence_of` splits on any `[.!?]` + whitespace, which invents
   boundaries at "Art. 9");
2. ask for the **complete final sentence**, given the surviving sentences as
   context and the cut sentence verbatim;
3. accept it only when it is exactly ONE sentence, terminates, opens with the cut
   sentence's own opening words, keeps its substance (content-word recall ≥ 0.8),
   does not re-answer the earlier sentences, and does not weld a new clause onto a
   closed one (`_welds_new_clause`: a bare finite verb directly after a fragment
   whose trailing clause already has its own predicate).

`splice` restores the R357 behaviour byte-for-byte (deny-list: an unrecognised
value keeps `splice`). Registered in `_engine_cache_key`.

## 3. Gate — passing rows are NOT touched (deterministic, no provider calls)

`tail_repair_gate.py --part 1` runs every recorded live answer through the real
guard with the Stage-2 provider **stubbed to raise if called**:

| corpus | checked | byte-identical | fired |
| :--- | ---: | ---: | ---: |
| `official-r286-easy-live` (110 gold rows) | 110 | 110 | 0 |
| `easyhard-r411-fullsys-full-A` | 132 | 132 | 0 |
| `easyhard-r411-fullsys-hard-A` | 37 | 37 | 0 |
| `easyhard-r411-fullsys-singleturn-easy-A` | 134 | 134 | 0 |
| **total** | **413** | **413** | **0** |

Zero provider calls, zero bytes changed on any complete answer.

## 4. Gate — real truncations, paired arms, n=40 (live, wrapper-served)

40 official-gold rows, each answer cut mid-final-sentence at a word boundary
(`cut=0.6`), the SAME cut run through both arms by the real guard, with the
deterministic Stage-1 answer production would fall back to. 0
`bedrock_auto_fallback` in either arm — the wrapper carried both.

### 4a. Grounded grammar diagnostic (vs the ORIGINAL un-truncated prose)

`grounded_repair_diagnostic.py` — no model calls. "Glue" = a shipped token absent
from the original that splits into two tokens both present in it.

| metric | splice | sentence |
| :--- | ---: | ---: |
| rows with a GLUED word | **17 / 40** | **0 / 40** |
| rows with a fabricated coordinate | 8 | 4 |
| citations lost vs the cut text | 3 | **1** |
| citations the cut dropped and the repair restored | 1 | **4** |

⚠ Honest scope note: the **clause** weld the R411 report described did NOT
reproduce on these 40 mechanically-derived cuts (0/40 in both arms — the cuts land
mid-clause, where a tail completion is grammatical). The defect that DID reproduce
at scale is the **space-loss glue** (17/40), which the fix also eliminates by
construction, because the model re-emits the whole sentence instead of guessing a
join boundary.

### 4b. All eight official axes

Filled in by `tail_repair_gate.py --score` (see §6).

## 5. Void-run self-detection (the R412 measurement failure, fixed in the harness)

R412's 95+95 pair printed a plausible **null** — no speedup on any axis — and was
**VOID**: 189 `bedrock_auto_fallback` lines, i.e. the tunnel was down and Bedrock
(which always receives the full `system`) served BOTH arms. A void delta and a real
null delta are the same shape, so this cannot be left to the reader.

`evals.harness.gate_validity` + wiring in `easyhard_ab` now VOID a paired run and
**withhold the delta table** (exit code 3, banner printed) when:

* either arm was served by the **FALLBACK** transport (`fallback_ok > 0`);
* an off-contract transport was **refused** (`refused > 0` — R360 policy);
* rows were produced with **ZERO Stage-2 completions** on either leg;
* the transport provenance is **unreadable**;
* a declared **system-slot lever** dispatched **IDENTICAL** system payloads to
  both arms (or the payload could not be observed).

The system payload is hashed at the **provider seam** (`OpenAIWrapperRequest.system`)
because the substitution happens INSIDE
`_openai_wrapper_complete_for_graph_rag` — hashing the engine function's arguments
records the pre-substitution text and reports two different arms as identical.
That mistake was made and caught here: the first cut of the probe VOIDed a
correctly-served run.

### Validation (real runs, both directions)

| run | transport | verdict | exit |
| :--- | :--- | :--- | ---: |
| `--baseline-env REGENOLD_STAGE2_FULL_SYSTEM_SINGLE_TURN=0 --branch-env =1`, primary dead (`OPENAI_API_BASE=127.0.0.1:1`) | Bedrock served both arms | **VOID** — 2× fallback reason + identical system digest | 3 |
| same lever, wrapper healthy | wrapper served | **VOID** — silently fell back mid-run, correctly refused | 3 |

The first run is the R412 case reproduced on demand, and its **latency p50 read
32.9 s vs 20.7 s** — a plausible-looking effect that would have been reported as a
result.

## 6. The join was a GUESS, and the transport destroys the signal

The R357 tail rung expressed the join boundary as LEADING WHITESPACE: the prompt
asked the model to begin the tail with a space at a word boundary and to
continue the word with no space mid-word, and the splice read `tail[:1].isspace()`.
Nothing may assume a completion's leading whitespace survives the provider.

MEASURED live (`hospital_case_probe.py`, primary leg, `fallback_ok=0`) — the R411
production sentence, driven through the real guard:

```
... queries on a hospital websiteArticle 50(1), requiring that patients be ...
```

The identical defect class was already 17 of 40 rows in the objective
grammar diagnostic (§4a). Fixed generally, for BOTH modes:

* the tail prompt now requires a `GAP:` (rest of the sentence) or `CONT:`
  (characters that finish the cut word) marker. A token survives the trim that
the whitespace signal does not. `_join_tail_to_fragment` decides the join from
the marker and logs the boundary it took;
* a tail that ignores the protocol joins on a WORD boundary — that failure mode is
  two visible words, where the old default manufactured one nonsense word;
* **rung 0, TERMINATE** — when the cut sentence is already grammatical and wants
  only its full stop, the repair IS that full stop. The detector
  (`_fragment_terminates_cleanly`) cannot tell a whole final word from one cut
  mid-word, so it only decides whether the ECHO option is OFFERED; the echo is
  accepted only when it is BYTE-IDENTICAL to the cut sentence, so this rung
  cannot paraphrase a provision away. Re-verified live:

```
... duties it triggers are those in answering general patient queries on a
    hospital website.                        ← one sentence, no glue, no weld
```

* the reconstruction prompt was under-completing. MEASURED on the §4b gate: the
  two worst regressions (rg_034 4/4 → 0/4, rg_049 1/3 → 0/3) were the model
  HEDGING where the splice named the provision. rg_034's cut sentence ends
  "... the remedial actions available to the Court" and the old prompt produced
  "... would instead derive from the provisions governing ..." — naming no power
  at all. The prompt now requires the operative content and names that failure
  verbatim. Re-verified live on the same shape: the reconstruction now returns
  "... **Article 100(5)**, which confers unlimited jurisdiction ... and to
  **cancel, reduce or increase the fine** imposed" — the exact criteria the splice
  had and the old reconstruction lost.

## 7. Gate outcome — the default does NOT flip, and the reason is the judge

Part 1 (deterministic, provider stubbed to raise) re-ran with the new prompt and
the marker protocol: **413 of 413 recorded complete answers byte-identical, 0
provider calls**, across all four corpora. The "does not touch passing rows"
contract holds.

Part 3's judge leg came back **VOID** and must not be read: the wrapper's
Claude-Max OAuth expired mid-run, so the freshly written splice scorecard has
`ans_correctness_loose` **3.76 %** and `regulatory_tone` **2.5 %** (the judge
returns nothing) against 75.9 / 92.5 in the recorded identity. Its REFERENCE
axes are still valid — they are computed deterministically from the reference
lists: `ref_loose` **90.54 in both arms**, `ref_strict` 72.52 (splice) vs 69.82
(sentence, previous prompt), `ref_conc` 53.92 vs 53.33.

So the §4b table cannot be re-read against the new rungs, and the honest
decision follows from that:

* **default stays `splice`** — the reconstruction rung ships behind the
  default-off `sentence` mode until a judge leg carries both arms;
* the two fixes that are unconditional ship now, because each is verified with a
  deterministic instrument or a live reproduction rather than a judge: the
  marker-protocol join (applies to BOTH modes) and the under-completing prompt
  (inside `sentence` mode).

## 8. Open items

* **Re-run the 8-axis gate when the wrapper's OAuth is live** (`login.bat`), then
  the `sentence` default decision is one run away: the rungs and their pins are
  in place and the arm runner already exists (`run_arm_b.py` re-uses a completed
  arm).
* The Bedrock judge profiles for Sonnet 5 / Opus 5 are `api_access_denied_403` on
  the current key vintage; `eu.anthropic.claude-opus-4-6-v1` is the top model
  reachable there and is the fallback judge (a different identity, so it is a
  second read, not a substitute for the recorded one).
* `prompt_ab.py` already raises on `fallback_attempts`/`primary_failed` for the
  wrapper arm, so it needed no wiring; the gap was in the paired gate.
* A judge leg that returns nothing produces plausible-looking zeros. The paired
  harness VOIDs on transport, but `score_arm` does not check whether the judge
  actually answered — a `tone`/`ans_loose` of 2.5 % is the tell, and the next
  round should make that a hard error rather than a readable number.

---

## 9. SOTA roadmap row 2 (Ref-minimality) — FALSIFIED, with the bound that closes it

`docs/measurements/r413/ref_minimality_ceiling.py` (deterministic, no provider
calls, two independent frozen ledgers). Run:

```
.venv/Scripts/python.exe docs/measurements/r413/ref_minimality_ceiling.py
→ docs/measurements/r413/ref-minimality-ceiling.json
```

The lever is exactly computable offline because `Ref Conciseness` is a pure
COUNT ratio — `(min(|P|,|G|) / max(|P|,|G|))²` over ARTICLE/ANNEX heads — while
`Ref Correctness (Loose)` is recall and `(Strict)` is F1. So the whole trade is
visible without generating a single token.

| ledger | rows | heads | excess |
| :--- | ---: | ---: | ---: |
| `official-r286-easy-live` (n=110 gold) | 102 | 268 | **162 (60.4 %)** |
| `official-r407-…-hard` | 102 | 277 | **160 (57.8 %)** |

**1. No shippable form exists.** A head-level prune is SHIPPED-eligible only when
it drops ZERO expected heads; on both ledgers the best lossless candidate is
**NONE**:

| candidate | removed | expected LOST | Δref_conc | Δoverall |
| :--- | ---: | ---: | ---: | ---: |
| A drop heads the prose never cites (the R411 form) | 17 | 4 | +1.69 | **−0.24** |
| B drop heads confined to an enumeration dump | 16 | 2 | +2.07 | +0.26 |
| C drop heads whose last mention is past 70 % of the prose | 98 | 34 | +8.60 | −2.81 |
| D cap the list at the median gold size K=1 | 166 | 54 | +46.50 | **−0.68** |

(Same ordering on the hard ledger: A −0.80, B +0.25, C −6.50, D −1.99, no
lossless candidate.) The four forms fail at three different places — A and C
delete expected refs, and the two that do not (B/D) trade recall for count.

**2. The features carry no signal at all.** Rank-AUC, excess heads vs
expected-and-present heads, on the easy ledger: `never-cited` **0.521**,
`dump-only` **0.534**, `late-mention` **0.597** (hard: 0.516 / 0.524 / 0.538).
An AUC of 0.52 means the feature ranks an excess head above an expected one
essentially by coin flip — so no threshold, classifier or cut-off in this family
can separate them, which is the general reason the last four attempts failed
rather than four separate misfortunes.

**3. The oracle ceiling does not reach the threshold either.** Even a PERFECT
classifier of the same feature, applied only to excess heads, buys
`never-cited` **+1.26 pp**, `dump-only` **+0.85 pp**, `late-mention` **+4.18 pp**
overall on the easy ledger (+0.78 / +0.27 / +3.65 on hard) — and the only
ceiling above the roadmap's +2.2 pp is `late-mention`, whose real threshold (C)
loses 34 expected heads and **−2.81 pp**.

**Why the class is closed, in one line.** `ref_conc` is a length ratio; loose and
strict are content recalls; the official aggregate is a GEOMETRIC mean. Dropping
heads can raise conciseness arbitrarily (candidate D reaches `ref_conc` 85.76,
+46.50 on the baseline) and still LOSE overall, because every dropped expected
head costs recall in the same product. **Conciseness is therefore not tradable
against recall under this rubric**, and the reference headroom that remains is
`Ref Strict`'s GRAIN (roadmap row 4 — sub-points on already-correct heads), not
the COUNT of heads. Row 2 is closed on evidence; re-opening it requires a form
that beats the oracle ceiling above, not another heuristic.

Scope note: both prediction and gold are folded onto heads (what a head prune
acts on), so these absolute axis values are not scorecard values, and the cost of
losing an expected head is under-stated (its sub-points vanish with it). Both
biases push the same way, so the falsification is not rescued by grain.
