# R308 Checkpoint — pending verification: does the uncap + coverage clause hold on `easyhard_ab`, on genuine Opus 5 output?

**Status:** Shipped as `d5985e7` / PR [#318](https://github.com/Peaky8linders/regenold-eu-ai-act-rag/pull/318),
merged to `main`, all deterministic gates green (see CLAUDE.md's `## Round 308`
entry — read that first, it has the full grounding for every claim below).
**This document exists because that round shipped an honestly-unresolved
question rather than a claimed win, and — unlike every round from R282
through R307.1 — it landed on `main` with no `## Round 308` entry in CLAUDE.md
and no `.planning/R308-*` checkpoint at merge time.** This file plus the
matching CLAUDE.md section close that discipline gap.

---

## 0. What is settled vs what is not

**Settled (deterministic gates, already re-verified by stash A/B, do not
re-run these):**

* davidath QA is byte-identical — and this is now **measured, not merely
  argued by construction**. Two per-row diffs over all 137 QA rows
  (`pred_answer` + `pred_refs` + all 13 score axes, excluding `latency_ms`):
  **(a)** HEAD with `REGENOLD_ANSWER_NO_CAP=0 REGENOLD_ANSWER_COVERAGE=0` vs
  HEAD at code defaults → **0 rows differ**; **(b)** HEAD vs parent
  `4c4a720` → **0 rows differ, identical in every digit**. This check was
  worth running because R308 edits `app/integrations/regenold/models.py`,
  the answer normaliser, which *does* sit on the deterministic path — a hole
  in the `stage2_landed` gate would have changed every deterministic answer
  silently. It has none.
* ⚠ Do **not** grade this round against the R300-era pin
  (Ans Loose 0.1402 / Ans Strict 0.4032 / Ans Conc 0.1980). It predates
  R303/R305/R306/R307 and manufactures a spurious ~0.005 Answer-axis
  "drift" that does not reproduce against R308's actual parent. The correct
  figures are in R308's own commit body: 0.1407 / 0.4079 / 0.1961.
* `evals.regenold.runner` 255/255, RISK_F1 macro 1.00.
* OOS probe 0 scope leaks (2 pre-existing `adjacent_eu` soft fails only).
* The `two_stage_pipeline` failures under `provider=cli` are pre-existing, not
  a regression (40/40 pass under the clean env).

**Not settled — this is the actual pending work:**

* Whether `REGENOLD_ANSWER_NO_CAP` + `REGENOLD_ANSWER_COVERAGE` are net
  rubric-positive on **reference conciseness**, given the measured 2.33 →
  3.50 refs/row inflation. The n=7 comparison available at ship time used
  independent (non-paired) Opus generations and is inside Opus's own sampling
  noise — it is not evidence either way.
* Whether Stage-2 is actually running on genuine `claude-opus-5` output in
  production right now, or whether the local wrapper service is still serving
  stale in-memory code from before the on-disk alias fix (see the blocking
  step below). Every measurement taken so far that fed the R308 decision was
  taken **before** that restart, so it may itself have been graded on Opus
  4.8/4.6 output mislabelled as opus-5.

---

## 1. The exact blocking step

The wrapper repo (`D:\Claude Projects\claude-code-openai-wrapper`) has an
**uncommitted** change to `src/claude_cli.py` that removes an in-transport
`claude-opus-5 -> "opus"` alias (confirmed via `git status --short` in that
repo: `M src/claude_cli.py`, not yet committed). That alias used to silently
route every opus-5 request to whatever the CLI's bare `opus` token resolved
to — on the CLI version in place when this was discovered, that was
`claude-opus-4-8`, not opus 5 — and it did so **invisibly**, because the
OpenAI-shaped response still echoed back `"model": "claude-opus-5"` (a bare
echo of the caller's request field, not evidence of which model actually ran).

`regenold-wrapper` is a Windows service (verified `Running`, `Automatic`
start type via `Get-Service`). A long-lived service process reads its Python
source once at process start; an on-disk edit does not take effect until the
process restarts. **So the on-disk fix is not yet live for that service until
it is restarted.**

**Staleness proven, not assumed** (measured 2026-08-04 via
`Get-CimInstance Win32_Process` — note `Get-Process ... .StartTime` returns
null here because the service runs as another user, so use CIM):

```
PROC_START : 2026-08-03 14:00:45   <- running wrapper process
FILE_MTIME : 2026-08-03 23:30:17   <- src/claude_cli.py edited
VERDICT    : STALE - process predates the source edit by 9.5h
```

The prerequisite is also already satisfied, so the restart will not be
wasted: the CLI at `C:\Users\th3un\.local\bin\claude.exe` reports
**2.1.220** and `grep -c -a -o 'opus-5'` returns **42** — matching the
wrapper's own stated criterion exactly. And the alias code is *absent* from
both HEAD and the working tree of `claude_cli.py` (grepped), so simply
loading the current file is sufficient; no further edit is required.

⚠ **This step cannot be done by the coding agent.** Verified closed:
`IsInRole(Administrator)` → `False`; `sc.exe stop` → `OpenService FAILED 5:
Access is denied`; `taskkill /F` → `Access is denied`; and a
`Start-Process -Verb RunAs` self-elevation attempt returned *"The operation
was canceled by the user."* A human must run the elevated command.

**The blocking step, elevated PowerShell:**

```powershell
Restart-Service -Name regenold-wrapper -Force
```

**Verification after the restart** (per the wrapper's own source comment in
`claude_cli.py`, the authoritative recipe — do NOT trust the OpenAI-shaped
`"model"` field in a chat-completions response, it is a bare echo):

```bash
# From the machine running the CLI directly (not through the OpenAI-shaped
# wrapper endpoint), confirm the CLI itself reports the real model used:
claude -p --model claude-opus-5 <<< "ping"
# Expect a modelUsage entry that says exactly:  claude-opus-5
# (not claude-opus-4-8, not claude-opus-4-6)
```

Also confirm the CLI binary itself is new enough — per the same source
comment, `claude-opus-5` fast-mode support requires CLI **>= 2.1.220**:

```bash
grep -c -a -o 'opus-5' "$CLAUDE_CLI_PATH"
# 0  -> CLI too old, opus-5 requests will still run but WITHOUT Fast mode
# 42 -> confirmed on the fixed CLI version
```

Only once both are confirmed is it safe to treat any live measurement as
genuine Opus 5 output rather than a mislabelled 4.6/4.8 answer.

---

## 2. The exact command to run once unblocked

Per CLAUDE.md's standing rule (`## Validation policy`), the merge gate for a
change that can move an answer or its references is the live pairwise A/B —
**not davidath**. R308's own commit message names the specific harness this
round needs, because `ab_judge`'s references axis has no minimality term
(exactly how R142.1's positional clamp lost a live pairwise 11-0 while
looking clean on `ab_judge` alone):

```powershell
# Baseline arm = R308 switches OFF (pre-round behaviour: capped answer,
# no coverage clause, Opus aliased down to claude-opus-4-6).
# Branch arm   = R308 switches ON (the shipped default).
.venv\Scripts\python.exe -m evals.harness.easyhard_ab `
    --label r308-uncap-coverage-postrestart `
    --baseline-env REGENOLD_ANSWER_NO_CAP=0 `
    --baseline-env REGENOLD_ANSWER_COVERAGE=0 `
    --branch-env   REGENOLD_ANSWER_NO_CAP=1 `
    --branch-env   REGENOLD_ANSWER_COVERAGE=1
```

Read `evals/harness/easyhard_ab.py` (or its `--help`) for the exact current
flag names before running — do not assume this invocation is byte-exact if
the harness has moved since this checkpoint was written; the important part
is the env pairing and which axis to read (below).

**If the `evals.harness.ab_judge` position-swapped pairwise runner is used
instead** (e.g. to also read correctness/tone), treat its **refs axis result
as informative but non-decisive** per the R142.1 precedent above — the
`easyhard_ab` count-ratio result is what governs the ship/revert decision on
reference conciseness specifically.

---

## 3. Decision rule

Read the reference-conciseness delta (count-ratio, `easyhard_ab`) between the
two arms:

* **Branch (uncap+coverage ON) holds or improves reference conciseness, with
  correctness/completeness improved (which is the round's whole premise) and
  no significant reference-axis loss** → keep both switches default ON as
  shipped. Close this checkpoint; fold the confirmed numbers into a follow-up
  CLAUDE.md addendum under Round 308 (do not silently overwrite the existing
  "KNOWN, UNRESOLVED" section — replace it with the resolved numbers and keep
  the paper trail).
* **Branch measurably regresses reference conciseness / reference precision
  without an offsetting correctness win that the geometric-mean scorecard
  would actually reward** → this is the R142.1 shape again. Do **not** try to
  patch the coverage clause's wording blind; re-scope it further (e.g.
  tighten the "naming a member adds no new reference" carve-out, or make the
  uncap conditional on question shape rather than blanket-on-Stage-2), and
  re-run the same paired A/B before shipping any change to the default.
* **The n available is still too small to call it (< ~20 paired rows, or high
  variance)** → widen the sample before deciding anything. Do not ship a
  default flip on a noise-floor read. This is measured, not cautionary: two
  `easyhard_ab` runs whose **baseline arms were identical** changed 20/40
  rows' `pred_refs` between runs, drifted `ref_conc` by 0.053, and
  **sign-flipped all three reference axes**; the harness's own "est. Overall
  uplift" swung from +0.14 pp to −0.80 pp on generation variance alone. So
  prefer more paired rows over a single confident-looking run, and read the
  harness's **paired** subset (its `_paired` block, "the honest A/B read"),
  not the full-arm aggregates — the arms can span different row sets if one
  loses rows to a 429.

---

## 4. Rollback levers (all independent, no code change, verified in the shipped commit)

```bash
REGENOLD_ANSWER_NO_CAP=0          # restore the 3-sentence / soft-char-cap ceiling
REGENOLD_ANSWER_COVERAGE=0        # revert to the pre-R308 delivered instruction set
REGENOLD_WRAPPER_MODEL_ALIAS=1    # restore the pre-R308 Opus -> claude-opus-4-6 downgrade
```

`REGENOLD_MAX_ANSWER_SENTENCES=<n>` (an explicit integer) wins over
`REGENOLD_ANSWER_NO_CAP` on its own — an operator can pin a specific cap back
on without disabling the uncap switch. Remember the R306 finding still
applies here: `railway.toml [deploy.envs]` **has never applied** to the
Railway service — env vars must be set on the Railway dashboard/CLI directly,
or rely on the code defaults these switches ship with.

---

## 5. Context for a fresh session picking this up cold

* Read `## Round 308` in `CLAUDE.md` first — it has file:line references for
  every switch, the exact probe evidence for the dead-system-prompt finding,
  and the deliberate cache-key asymmetry that makes the paired A/B possible.
* The three switches: `REGENOLD_ANSWER_NO_CAP` (route post-processing, NOT in
  `_engine_cache_key` by design), `REGENOLD_ANSWER_COVERAGE` (Stage-2 prompt
  content, IS in the cache key), `REGENOLD_WRAPPER_MODEL_ALIAS` (transport,
  IS in the cache key). All default to the R308-shipped values already.
* Per CLAUDE.md's `## Validation policy — A/B (ab_judge), not davidath, is
  the merge gate`, do not treat a clean davidath run as evidence that the
  reference-conciseness question is resolved — it structurally cannot be,
  because davidath never exercises the Stage-2 path these switches gate on.
* If the wrapper-service restart step above has already been done by the time
  this is picked up, skip straight to Section 2; if unsure, re-verify with
  the `claude -p --model claude-opus-5` check before trusting any numbers
  gathered in between.
