# R427 — R426 T1: one Stage-2 leg-2 dispatch, gated by a byte-identical replay

**Verdict: SHIPPED as a pure move.** 774/774 drives byte-identical (258 inputs ×
3 call-site drives), every drive proven to have reached the code it claims to
measure, and the gate shown to FAIL when the deferred change is applied.

## 1. What moved

| before | after |
| :-- | :-- |
| the leg-2 verdict written twice — `_try_bedrock_fallback` (inside `_openai_wrapper_complete_for_graph_rag`) and an inline block in `_claude_max_enhance_answer` | one `dispatch_leg2` in **`app/llm/stage2.py`**, one `Stage2Outcome`, one `record_result` |
| the emptiness rule, the truncation rule and the counter timing were properties of a *call site* | they are properties of a **named preset** (`PRESET_TRANSPORT`, `PRESET_ANSWER`) declared in one table, with the divergence documented instead of implicit |

`dispatch_leg2(text, preset=..., structurally_truncated=...)` returns
`Stage2Outcome(text, leg, rejected, ok)`. The text is carried **verbatim** — the
dispatch never rewrites an answer — and the recording happens on the deferred
outcome, in the dispatch and nowhere else, so
`fallback_attempts == fallback_ok + fallback_failed` holds whichever site dialled.

Two direct `record_result(..., ok=False)` calls survive, and should: they are the
exception handlers for a *raising* leg-2 dial (R361). A test asserts no
`STAGE2_FALLBACK, ok=True` record exists anywhere else in the engine.

## 2. Why the presets are not equalised

Three real divergences existed between the copies. All three are now visible in
one place and deliberately **preserved**:

1. **Counter timing.** The transport copy defers the verdict until the text has
   survived the rejection rules (R361); the answer copy recorded `ok=bool(text)`
   the moment Bedrock replied.
2. **Emptiness.** Transport: falsy is empty (`not text`), so `"   "` **ships**.
   Answer: stripped-empty is empty.
3. **Truncation.** Transport rejects a mid-clause leg-2 answer; the answer copy
   did not apply the rule at all.

Equalising 2 and 3 changes **which text ships**, which is a behaviour change, not
a move — and the audit's rule is explicit that a move must not bundle one. It is
**T1b** (§6), and the sensitivity probe (§4) measures that the two presets
differ on exactly four corpus inputs today.

## 3. The gate — a differential replay, not a scoreboard

A row-level recorded-draw replay is not available for this move: the transport
decision happens **upstream of generation**, no board checkpoint stores the raw
leg-2 text, and re-calling the models is not byte-reproducible. What the decision
*is* a pure function of is the leg-2 response text plus which call site dialled
it — so the gate drives **both real implementations** over one corpus and diffs
the observable consequences:

* the text the caller receives (byte-for-byte),
* the `stage2_policy` counter delta (a drifted `record_result` cannot hide),
* the R417 leg-2 serve marker,
* every warning emitted (the discard is usually only visible as a log line).

**Corpus** — 258 inputs:

* **250 recorded answers** from the gated boards (`r424-preamble`, `r423-need4`,
  `r423-need`): production-shaped legal prose at 103–2,329 chars, including
  recorded texts that are *shaped* like a truncation;
* **8 class boundaries** the branches actually key on: `None`, `""`,
  whitespace-only, a mid-clause cut, a complete sentence, an `<answer>`-wrapped
  complete answer, a markdown table row, an ellipsis cut.

**Three drives per input**, because the answer path never reaches its inline
block the way the transport does:

| drive | leg 1 | what it exercises | dials (primary, fallback) |
| :-- | :-- | :-- | ---: |
| `transport` | transport error 500 | `_try_bedrock_fallback`'s verdict | (1, 1) |
| `answer` | `finish_reason=length` | the real chain end to end (leg 1 raises out; the answer path's outer handler returns `None`) | (1, 1) |
| `answer_block` | stubbed to `None` (seam, §6) | the answer path's **inline block**, the second site moved | (0, 1) |

The dial counts are the **non-vacuity proof**, in the R422/R425 tradition: an
equivalence result over a call site that never ran is worth nothing. An earlier
version of this harness reported `answer-site dials [1]` and was correctly
refused as VOID; the answer drive above is the response to that.

**Result: 774/774 drives byte-identical**, all three drives REACHED.

## 4. Falsification — the gate was shown to fail

`docs/measurements/r427/sensitivity.py` perturbs exactly one thing — the T1b
change — re-runs the differential in a separate process (the engine binds
`dispatch_leg2` by name at import, so an in-process perturbation would leave the
loaded module untouched and report a false "insensitive"), then restores the file
and verifies the restore by SHA-256.

```
=== unperturbed: the shipped move ===
  774/774 drives byte-identical (258 inputs x 3 call sites)  (exit 0)
=== perturbed: PRESET_ANSWER applies the truncation rule (the T1b change) ===
  770/774 drives byte-identical (258 inputs x 3 call sites)  (exit 1)
restored app/llm/stage2.py: OK  (bdb6eb633fbcdf75)
SENSITIVE — the gate refused the deferred change, as a pure move must
```

The four inputs it catches are `mid_clause_cut`, `ellipsis_cut`, `recorded[10]`
and `recorded[42]` — two synthetic boundaries and **two recorded production
answers**, i.e. the corpus is discriminating on real draws, not only on fixtures.

## 5. Recorded-draw context (why the row-level replay is +0 by construction)

Across the 50 recent board checkpoints (1,229 rows),
`provenance.stage2_served_by` is `primary` 785, `deterministic` 149,
`prior_turn` 4, empty 291 — and **`fallback` 0**. No recorded row on any of these
boards was ever served by leg 2, so the shipped change cannot move a recorded row
on any graded axis. The differential above is therefore the operative
equivalence proof, and it is run over the real code on both sides rather than a
transcription of the old branches.

## 6. Findings this move surfaced (both are new)

**F1 — the answer path's inline leg-2 block is unreachable today.** The block is
only entered when the wrapper *transport* returns `None`, and **no shipped branch
does that**: every leg-1 failure either returns leg 2's own answer or raises
(`response.error`, `finish_reason="length"`, structural truncation, off-contract
base URL, provider raise — all measured; the raise is caught by the answer path's
outer handler, which returns `None`). So the duplicate policy this round retires
was not merely duplicated — it was **dead code carrying a second, drifted copy of
a policy that a future branch change would silently reactivate**. That is a
stronger argument for the move than the line count, and it is why the
`answer_block` drive exists.

**F2 — the recorded corpus itself contains truncated-shaped answers.** 162
recorded answer fields end without sentence-terminal punctuation. That is
expected (the wire ships the *polished* answer, and the R357 tail-repair path
exists for exactly this), but it means "the model sometimes ships a cut answer"
is measurable in the recording, not hypothetical — relevant to T1b.

## 7. T1b — the equalisation, deferred with its gate named

The change: apply the structural-truncation rule on the answer path too
(`PRESET_ANSWER` rejects `REJECT_TRUNCATED` rather than only counting it), and
let the inline block fall through instead of shipping cut text.

Why it is not in this ship: it changes **which text ships**, so it cannot be
carried by a byte-identical replay (the sensitivity probe is precisely the
evidence that the two differ), and it must be measured on the graded axes like
any other answer-changing lever — the R357 tail-repair path already exists for
that class, so the first question for T1b is whether it is redundant with the
repair rather than additional to it. Reachability (F1) bounds its blast radius
today to whatever makes leg 1 return `None`.

## 8. Validation

* `tests/test_r427_stage2_leg2_dispatch.py` — 17 cases: the shipped semantics of
  both presets, verbatim passthrough, the counter invariant, the loud unknown
  preset, the two-call-site wiring, no surviving `ok=True` record, and no
  module-level engine import (no cycle).
* `227 passed` across the transport, instrument, raising-primary, host-parsing,
  cache-key, tracked-import, truncation-guard, XML-channel and two-stage suites.
* Lint parity with HEAD on `_graph_rag_impl.py` (34 pre-existing findings both
  sides, none from this change); `app/llm/stage2.py` clean.
* `test_r394_2_tracked_module_imports` warned exactly as designed while
  `app/llm/stage2.py` was untracked — it is staged with this commit.

## 9. Reproduce

```
.venv\Scripts\python.exe -m docs.measurements.r427.t1_leg2_differential --json
.venv\Scripts\python.exe -m docs.measurements.r427.sensitivity
.venv\Scripts\python.exe -m pytest tests/test_r427_stage2_leg2_dispatch.py -q
```

Artifacts: `t1_differential.jsonl` (a header carrying the corpus digest and HEAD,
then one line per drive: returned-text digest and length, the raise, the dial
count, the counter vector, the serve marker and the warning digest, OLD and NEW
side by side; full text and warning list are recorded for any side that
disagreed), `t1_leg2_differential.py`, `sensitivity.py`. Storing both sides in
full on all 774 drives produced a 2.5 MB artifact for a result that is 774
identical rows, so the digests are the evidence and the text is kept only where
it is needed to debug.
