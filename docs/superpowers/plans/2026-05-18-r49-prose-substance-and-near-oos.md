# R49 — Consistency-Guard Prose Substance + near_oos Bypass

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close two R47/R48 regressions: (A) the R48 consistency guard's generic 1-sentence template that regressed V2 multi-turn coherence 0.28 → 0.08 and tricky keyword recall 0.26 → 0.20; (B) the 3 V2 `near_oos` rows (DSA / NIS2 / PLD lookalikes) that currently fall through to `zero_retrieval_fallback` and ship spurious AI Act citations.

**Architecture:**
- **R49-A**: New `app/integrations/regenold/grounded_prose.py` stitches 2-3 sentences from `EC_CHECKER_OBLIGATION_MAP` summaries when the route's R48 final-pass guard fires. Route's consistency guard calls it instead of `_build_prose`. Existing 3-sentence + 600-char soft cap preserved.
- **R49-B**: Add `ScopeReason.NEAR_OOS` + `_NEAR_OOS_PATTERNS` to `scope.py`. Detection runs in `classify_scope` after non-existent-article check, before any in-scope signal — explicit Art. N refs still win, but lookalike DSA/PLD/NIS2 phrasings bypass retrieval. `refusal_copy_for` returns a framework-specific pointer.

**Tech Stack:** Python 3.12, stdlib + same-package imports only. No new dependencies.

---

## File Structure

- **Create**: `app/integrations/regenold/grounded_prose.py` (~80 LOC)
- **Modify**: `app/routes/regenold.py` lines 1990-2014 (consistency guard call-site)
- **Modify**: `app/integrations/regenold/scope.py`:
  - `ScopeReason` enum (+1 value)
  - `ScopeVerdict` dataclass (+1 optional field)
  - `_NEAR_OOS_PATTERNS` module-level constant (new)
  - `_detect_near_oos_framework` helper (new)
  - `classify_scope` — insert detection at the right precedence
  - `refusal_copy_for` — handle the new reason
- **Create**: `tests/test_grounded_prose.py` (~100 LOC)
- **Create**: `tests/test_near_oos.py` (~120 LOC)

---

## Task 1: R49-A — `grounded_prose` module

### Step 1: Write the failing test
Create `tests/test_grounded_prose.py` covering:
- KB summary tokens appear in output for known refs (Art. 51 → "10^25", Art. 27 → "Fundamental Rights")
- 3-sentence + 600-char cap respected
- No refusal markers in output
- Graceful fallback to generic prose when refs have no KB entry
- Single ref / two refs / three refs render correctly
- Annex refs handled correctly

### Step 2: Run test to verify failure (module doesn't exist)

### Step 3: Implement `app/integrations/regenold/grounded_prose.py`
- Public API: `stitch_grounded_prose(internal_refs: list[str]) -> str`
- Reads each ref's `summary` from `EC_CHECKER_OBLIGATION_MAP`
- Strips leading `"Art. N:"` prefix from the summary (some R23 ports carry it)
- Sentence 1: "This question is covered by the EU AI Act under {refs}."
- Sentences 2-3: trimmed summary content from the top-2 refs, joined to fit 600-char cap and 3-sentence limit
- Falls back to current `_build_prose` behaviour when refs are unknown / KB stubs are missing

### Step 4: Run test to verify passes

### Step 5: Wire into route consistency guard
Edit `app/routes/regenold.py` lines 1990-2014:
- Replace `from app.engines.zero_retrieval_fallback import _build_prose` with `from app.integrations.regenold.grounded_prose import stitch_grounded_prose`
- Call `stitch_grounded_prose(internal_refs)` instead of `_build_prose(internal_refs)`
- Keep exception-swallow wrapper intact

### Step 6: Add integration test in `tests/test_consistency_guard.py`
Update the existing test that verifies the guard fires to assert the new prose contains substantive content (not just "Consult the cited provisions").

### Step 7: Run full pytest suite
- All existing R48 tests should still pass
- New tests should pass

### Step 8: Commit
```
git add app/integrations/regenold/grounded_prose.py app/routes/regenold.py tests/test_grounded_prose.py tests/test_consistency_guard.py
git commit -m "R49-A: substantive consistency-guard prose from KB summaries"
```

---

## Task 2: R49-B — `near_oos` detection + bypass

### Step 1: Write the failing test
Create `tests/test_near_oos.py` covering:
- Each V2 near_oos scenario produces a refusal with the correct framework name surfaced in the prose
- Out-of-scope test set (Netflix "withdraw subscription", "queen withdraw") stays in `CONVERSATIONAL` or `OTHER_REGULATION` refusal class (no false positive)
- In-scope questions that mention adjacent framework names (e.g. "Does our existing GDPR DPIA satisfy Article 27 FRIA?") stay `IN_SCOPE`
- Explicit Art. N refs override near_oos detection (e.g. "Article 13 transparency for VLOPs" → IN_SCOPE)

### Step 2: Run test to verify failure

### Step 3: Add `NEAR_OOS` to `ScopeReason` + optional `near_oos_framework` to `ScopeVerdict`

### Step 4: Add `_NEAR_OOS_PATTERNS` constant
- DSA / VLOP / "very large online platform" / "content-moderation AI" / "algorithmic transparency" + (no AI Act anchor) → "Digital Services Act"
- PLD / "product liability" / "AI-Act liability" / "civil liability" / "property damage" / "damages" → "Product Liability Directive"
- NIS2 / "cyber-resilience" / "essential-services entity" / "essential services" / "SOC operations" → "NIS2 Directive"
- Cyber Resilience Act / CRA when paired with "cyber resilience" → "Cyber Resilience Act"

Each pattern is a tuple `(compiled_regex, framework_name, short_handle)`. The detector requires the lookalike phrase AND must NOT be overridden by an explicit Art. N reference (handled by placement in `classify_scope`).

### Step 5: Add `_detect_near_oos_framework` helper

### Step 6: Insert detection in `classify_scope`
Between the non-existent-article check (step 3 in `classify_scope`) and the in-scope checks (step 4). Position matters:
- After non-existent-article check (so unknown Art. refs still get tailored refusal)
- Before known-ref check (so a phrase like "VLOP content moderation under Article 17" is still treated as DSA, not AI Act)
  - **Reconsider**: explicit Art. N reference should win — see test step 1 spec. Final position: AFTER known-ref check, BEFORE anchor check.

### Step 7: Extend `refusal_copy_for` to handle `NEAR_OOS`
Copy: "This question is about the {framework_name}, not the EU AI Act (Regulation 2024/1689). I only answer EU AI Act questions; please consult the {framework_name} text for the applicable rules."

### Step 8: Run full pytest suite

### Step 9: Run the V2 runner against TestClient to verify near_oos rows score perfectly
- Expected: tricky `near_oos` category → refL 1.0, refS 1.0, keyword recall ≥ 0.67 (DSA / NIS2 / PLD / "not the EU AI Act" tokens surface)

### Step 10: Commit
```
git add app/integrations/regenold/scope.py tests/test_near_oos.py
git commit -m "R49-B: near_oos detection bypasses zero-retrieval fallback for DSA/PLD/NIS2 lookalikes"
```

---

## Task 3: Run davidath bench parity check

### Step 1: Run the davidath bench against TestClient
```bash
.venv\Scripts\python.exe -m evals.bench.runner --label r49-testclient
```

### Step 2: Compare against R48/R47 byte-identical baseline
- Ans Strict shouldn't move materially (R49-A only fires inside the consistency-guard pathway which doesn't trigger on davidath)
- Ref axes shouldn't move (near_oos patterns don't substring-match any davidath QA)
- Latency may rise +1-2 ms (one extra regex pass per request)

### Step 3: If regressions detected, narrow patterns or guard further

---

## Task 4: Commit, PR, merge, redeploy, V2 re-run

### Step 1: Push branch + open PR
```bash
git push -u origin claude/affectionate-mccarthy-647aa7
gh pr create --title "round 49: substantive consistency-guard prose + near_oos bypass" --body ...
```

### Step 2: Wait for green CI

### Step 3: Merge PR

### Step 4: Wait for Railway redeploy
- Monitor `https://regenold-eu-ai-act-rag-production.up.railway.app/healthz/llm` for the new SHA

### Step 5: Run V2 live re-run
```bash
.venv\Scripts\python.exe -m evals.regenold.runner_v2 \
  --endpoint https://regenold-eu-ai-act-rag-production.up.railway.app/api/v1/regenold/eu-ai-act/ask \
  --label r49-live --verbose
```

### Step 6: Report scorecard
- Tricky: confirm `near_oos` category jumps to refL ≈ 1.0
- Tricky: confirm keyword recall lifts from 0.20 toward 0.30+
- Multi-turn: confirm coherence climbs from 0.08 back toward 0.28+
- Davidath QA: confirm no regression (re-run baseline if needed)
- Update CLAUDE.md scorecard table

---

## Acceptance criteria

1. All 1,433+ unit tests pass
2. Davidath bench TestClient run is byte-identical (or within ±0.003 noise band) to R48 baseline
3. V2 tricky `near_oos` category lifts refL 0.00 → 1.0
4. V2 tricky keyword recall lifts from 0.20 toward 0.30+ (R49-A contribution)
5. V2 multi-turn coherence lifts from 0.08 toward 0.28+ (R49-A contribution)
6. Silent-refusal rate stays low (no re-introduction of the R47 issue)
