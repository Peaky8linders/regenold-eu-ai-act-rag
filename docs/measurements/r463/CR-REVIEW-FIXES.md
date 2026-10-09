# R463 — CR-SKILL deep review of the branch, and the nine fixes it produced

`CR-SKILL.md` phase 1–3 run against `feat/finalize-recent-fixes-and-optimisations`
(43 files / +7489 at dispatch) with seven specialists in parallel. Full write-up:
`docs/reviews/feat-finalize-recent-fixes-and-optimisations-2026-10-09-08-39-46-24538c3.md`.
This note is the operational record: what changed, and what proved it.

## What was fixed

| # | Issue | Files |
|---|-------|-------|
| C1 | Zero Trust service token attached to **any** base URL | `evals/harness/frontier_baseline.py`, `evals/official/build_gold.py` (+ new `tests/test_r463_eval_cf_access_host_pin.py`) |
| C2 | R418 audit's statistics silently degraded without scipy, flipping a published reading | `docs/measurements/r418/kg_lever_ans_strict_repro.py`, `tests/test_r419_ans_strict_repro.py` |
| C3 | `OPENAI_TIMEOUT_SECONDS` missing from `_engine_cache_key` (invariant #4) | `app/routes/regenold.py` |
| I1 | Stage-2 call could die on its own telemetry (`message` null/string, `usage` non-dict, non-numeric tokens) | `app/llm/openai_wrapper_provider.py` |
| I2 | `/healthz/llm` accepted `inf`/`nan`/`0` timeouts; falsy spellings kept the billable probe ON | `app/main.py` |
| I3 | `content_hash` had two producers, two widths, and covered bytes that were not stored | `app/data/ontology_evidence.py`, `ontology_browse.py`, `ontology_ledger.py` |
| I4 | Two existence gates tested wire form against an internal-form key space (dead legs) | `app/data/ontology_browse.py`, `ontology_ledger.py` |
| I5 | `resolve_concept`'s shadow trace skipped 5 of 7 exits — under-counted the misses | `app/data/ontology_browse.py` |
| I6 | Evidence-bundle census counted headers, not the member lines level 2 drops | `app/engines/evidence_bundle.py` |
| I7 | Three tests that could not fail (tautology, source-scan wiring, judge env leak) | `tests/test_r460_length_control.py`, `tests/test_official_judge_model_compatibility.py` |

Reported and deliberately **not** changed: the zero-evidence `llm_ok` pass and the
`CF_ACCESS_HOSTNAME` pin are test-pinned designs; the `evidence_bundle`
four-space membership test is load-bearing (`_non_engaged_member_lines` says so
inline now, because this round's first cut widened it and deleted verbatim prompt
content — caught by the existing R460 pin).

## The R418/R419 statistics finding, in full

`_fisher_p`, `binomtest` and `wilcoxon` were lazy `scipy.stats` imports. scipy is
not a declared dependency (`requirements.txt:67` names it only inside a
transitive-note comment) and no CI job installs it. Consequences measured here,
with scipy absent:

* `_fisher_p` returned **1.0 for every table** — a 10/10 vs 0/10 separation read
  as "no separation", printed as `Fisher two-sided p=1.000`.
* the paired block returned `sign_p = wilcoxon_p = None`, and the `call` ternary
  read `None` as **"cost supported by the paired test"** with no test run, so a
  re-run printed the OPPOSITE of the committed artifact (`p=0.69` / `0.2304` /
  "cost NOT supported").

All three are now exact and scipy-free, and **reproduce the committed values**:

| | committed (scipy) | pure Python |
|---|---|---|
| Fisher, rg_010 shape 5/10 vs 6/10 | 1.000 | 1.0 |
| Fisher, rg_045 shape 5/10 vs 2/10 | 0.350 | 0.3498452 |
| Sign test, 14/11 | 0.69 | 0.69 |
| Wilcoxon, the 25 signed diffs | 0.2304 | 0.2304 |

The Wilcoxon is an exact subset-sum DP over doubled average ranks; the normal
approximation gives 0.226, which is why the exact route is the one kept. A driver
re-run with no scipy installed is **structurally identical** to
`docs/measurements/r418/kg-lever-ans-strict-repro.json`.

A second-order bug was caught while fixing the lint: `ranks` is built from the
NONZERO diffs while `diffs` keeps the zeros, so `zip(ranks, diffs)` paired the
wrong rank with the wrong sign whenever a zero was not last. The R418 pair has no
zeros (which is why the committed value matched anyway). The helper now aligns on
a same-filter sign list with `strict=True`, and
`tests/test_r419_ans_strict_repro.py` pins it with `[0, -6, -4, 1]` — correct 0.5,
misaligned 0.25.

**Lesson for the log:** "degrades conservatively" is only true of a *value*.
`return 1.0` on an uncomputable p was conservative for crediting a gain and
**wrong** as a reported statistic; `None` read through a truthiness test was not
conservative at all. An instrument that cannot compute its statistic must say so
in its own output, and a measurement helper must not depend on a package that is
not in `requirements*.txt`.

## Validation performed

* `pytest tests/test_r463_cr_findings.py tests/test_r463_eval_cf_access_host_pin.py`
  — new tests for C1/C3/I1/I2/I3/I4/I5/I6. Each was run **twice**: with the fix in
  place it passes, and with that fix's hunk reverted in the working tree it fails,
  so none of them is a test that would have passed anyway. Durable form of the
  proof: the assertions themselves — revert the hunk named for the finding in the
  review report and re-run the file. (The throwaway revert-and-rerun walker was
  written under `scratch/`, which is gitignored, and is not part of the commit;
  `git show 1aa130f -- <file>` is the hunk to revert.)
* R418 driver re-run → structurally identical JSON; `tests/test_r419_ans_strict_repro.py`
  11 passed.
* `ruff check` on every touched file: clean for the files whose findings are this
  round's. Pre-existing at HEAD and not touched: `evals/harness/frontier_baseline.py`
  (E702 ×4, F841, E741 — copied from `evals/official/judge.py`), `app/main.py`
  (W293, I001), `app/routes/regenold.py` (UP037).
* Full suite: `pytest tests/` (see the round's merge gate output for the counts).
* `git diff --stat docs/measurements/r388/official_gold_n110.jsonl` shows no
  change from the gold-correction script (the row is already `_revised: "R448"`).
