# R357 — post-generation truncation guard: detect → repair → fallback

**Scope:** the two-stage answer path (`_two_stage_generate` in
`app/engines/_graph_rag_impl.py`).
**Flag:** `REGENOLD_STAGE2_TRUNCATION_GUARD` (default **ON**, env-reversible),
folded into `_engine_cache_key` (R355 completeness gate green).
**Tests:** `tests/test_r357_truncation_guard.py` (41 cases) + the pre-existing
R142/R267/R91/R355 suites, all green.

---

## 1. Where the truncation was coming from (investigation, grounded)

The judge report describes the **pre-R356 R350.2** arm, so every failing row
was re-probed against the *current* code and the official provision text
before touching anything. Four distinct truncation surfaces exist:

| # | Surface | Status |
|---|---------|--------|
| 1 | **Token ceiling** — the R139 Opus thinking budgets (2048/4000) ate into `max_tokens`; long multi-obligation answers cut mid-final-sentence | **already fixed** (R257: `_stage2_answer_headroom` 1024→2048) |
| 2 | **Wrapper cut-stream** — Claude-Max reports `finish_reason="stop"` even when the stream cuts mid-word / mid-verdict | guarded at the wrapper (R102 structural, R142 incomplete-verdict) — but on a hit the ENTIRE polish is discarded and the deterministic Stage-1 answer ships |
| 3 | **The "…" hole** — `_looks_structurally_truncated` treated a trailing `…` as terminal punctuation, so a stream cut right after an ellipsis shipped a broken fragment | **fixed in R357** |
| 4 | **Dangling connector endings** — an answer ending on "…and", "…which", "…the" passed both wrapper guards (they only check terminal punctuation + three narrow R142 shapes) | **fixed in R357** (new detector) |

**Key insight:** the wrapper-level guards (surface 2) are *detect-and-discard* —
they throw away ~90% of a good polish because the final sentence was cut. The
R357 guard is *detect-and-repair*: it runs on the final text that would ship
and completes the truncated final sentence with one bounded LLM call, keeping
the surviving polish verbatim.

**Measurement against the judge rows (current code, Stage-1 deterministic):**

- `la_q13` / `la_q23` — the R356 curated intercepts already ship complete,
  citation-anchored verdicts; verified not truncated (normalised and raw).
- `la_q53` / `la_q72` / `la_q78` / `la_q86` — the Stage-1 answers (or the
  "no matching obligation" refusal) all end in complete sentences; the R357
  test suite pins this for all six rows and asserts the judge-quoted cut
  shapes ("internal-control. Article 10 requires", "…turn on whether") are
  detected.

## 2. What was shipped

### 2a. `_looks_structurally_truncated` — close the "…" hole
A complete regulatory sentence never ends in `…`; it was in the terminal set
since R102. Removed. An answer ending in an ellipsis is now treated as a cut
at every call site (wrapper + new guard).

### 2b. `_looks_incomplete_final_sentence(text)` — post-generation detector
`True` when the final answer would ship broken:
- structurally truncated (no terminal punctuation / ends `…`),
- R142 promissory verdict shapes (`"Applying that test to the facts."`,
  `"The operative reasoning."`, a trailing `:`),
- the final sentence dangles on a connector word (`and`, `or`, `which`,
  `the`, `of`, `under`, `with`, … — the R357 addition).

Conservative by construction: complete, period-terminated answers never fire it.

### 2c. `_attempt_stage2_tail_repair(...)` — bounded completion repair
One `_stage2_complete` call (same provider as Stage-2, temp 0 ⇒ deterministic
⇒ cacheable) asked for **only the missing tail**:
- the model continues mid-word with no space, or leads with a space at a
  word boundary (the boundary signal is the model's leading whitespace —
  the splice is a literal join, no guessing about the cut point);
- output that re-answers the whole thing, is over-long, is itself still
  truncated, or is empty → rejected → fallback;
- the repaired answer must pass `_looks_incomplete_final_sentence`.

### 2d. `_guard_stage2_truncation(...)` — wired into `_two_stage_generate`
Runs on the final `enhanced` text, after the drift / self-contradiction /
fidelity / faithfulness guards, right before the answer ships:
- complete polish → unchanged (`stage2_used=True`);
- truncated polish → tail repair; success ships the spliced answer
  (`stage2_used=True`), failure ships the complete deterministic Stage-1
  answer (`stage2_used=False`, so the R72 reconcile and verbatim gates treat
  it as deterministic — never a fragment).

### 2e. Prompt-side fix (the wrapper drops system messages — R282)
A COMPLETENESS-OF-THE-FINAL-SENTENCE clause on the Stage-2 **user** channel:
never stop mid-sentence, end with a full stop, never end with `…` / a
dangling connector / an unfinished clause. Wording-only ⇒ no citation effect
(clean on the reference axes). The repair guard remains the deterministic
backstop for whatever escapes the prompt.

### 2f. Cache-key registration
`REGENOLD_STAGE2_TRUNCATION_GUARD` flips `GraphRAGResponse.answer` (repair vs
deterministic fallback), so it is folded into `_engine_cache_key`
(R30/R56/R79/R263.2 doctrine). The R355 AST completeness gate passes.

## 3. Verification

- **41 new tests** in `tests/test_r357_truncation_guard.py`: detector
  fires/does-not-fire matrices, guard repair/fallback paths, real splice
  (clause + mid-word), repeat/empty/still-truncated repair rejection, flag
  gating, guard-off byte-identity, and the six judge rows never shipping a
  fragment.
- **Affected suites all green:** R357 (41) + R142 truncation (12) + R267
  submission (9) + R355 cache-key (2) + R91 truncation (12) + two-stage
  pipeline (7 standalone) + anthropic (21) + fusion (56).
- **Zero new full-suite failures.** The full-suite runs show 53 failures,
  every one traced to (a) the dead Claude-Max wrapper (`connection refused`
  — no wrapper process running), (b) a pre-existing cross-test pollution bug
  (`test_r267_submission_fixes.py` breaks `test_two_stage_pipeline.py` when
  run before it — reproduced identically at HEAD `9fd03c6` with none of these
  changes), or (c) `test_r267_general_answer.py`'s two wrapper-dependent
  tests, which fail identically with the guard disabled.
- **Deterministic bench byte-identity:** every new path is Stage-2-only
  (guard, detector, prompt clause); the deterministic Stage-1 path is
  untouched (pinned by `test_guard_off_is_byte_identical` + the Stage-1 row
  measurements).

## 4. Honest residuals

- The repair adds one bounded LLM call on the rare truncated-polish path —
  acceptable: the alternative (R102/R142 today) discards the whole polish.
- If the repair model omits the leading space at a word boundary the splice
  can glue two words ("productunder"); the prompt contract makes this the
  model's miss, not the guard's, and completeness validation still holds.
- The pre-existing `test_r267_submission_fixes` → `test_two_stage_pipeline`
  order pollution is a separate defect (leaks module state); it predates R357
  and is out of this round's scope.
